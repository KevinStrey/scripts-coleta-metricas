import argparse
import ast
import csv
from dataclasses import dataclass, field
import filecmp
import os
import shutil
from os.path import isdir
from pathlib import Path
import sys
import subprocess
import difflib

@dataclass
class EstadoMetricas:
    bom: int = 0
    fch: int = 0
    lch: int = 0
    frch: int = 0
    wfr: int = 0
    csb: int = 0
    csbs_base: int = 0  # NLOC no nascimento
    acdf_sum: float = 0.0

    tach_hist: list[int] = field(default_factory=list)
    chd_hist: list[float] = field(default_factory=list)

    # valores "ultima release"
    lca: int = 0
    lcd: float = 0.0

    def on_seen(self, release: int, nloc: int) -> None:
        if self.bom == 0:
            self.bom = release
            self.csbs_base = nloc

    def on_change(self, release: int, tach: int, loc_current: int) -> None:
        if self.fch == 0:
            self.fch = release
        self.lch = release
        self.frch += 1
        self.csb += tach

        chd = (tach / loc_current) if loc_current > 0 else 0.0

        self.tach_hist.append(tach)
        self.chd_hist.append(chd)

        self.lca = tach
        self.lcd = chd
        self.acdf_sum += chd

    def on_no_change(self) -> None:
        self.tach_hist.append(0)
        self.chd_hist.append(0.0)

    def finalize_release(self, release: int) -> dict:
        expected = release - self.bom + 1
        while len(self.tach_hist) < expected:
            self.tach_hist.append(0)
        while len(self.chd_hist) < expected:
            self.chd_hist.append(0.0)

        n = release
        wch = 0.0
        wcd = 0.0
        # mesmo criterio do original: historico ate a release anterior
        for i, r in enumerate(range(self.bom, n)):
            w = 2 ** ((r + 1) - n)
            wch += self.tach_hist[i] * w
            wcd += self.chd_hist[i] * w

        csbs = (self.csb / self.csbs_base) if self.csbs_base > 0 else 0.0
        acdf = (self.acdf_sum / self.frch) if self.frch > 0 else 0.0
        return {"wch": wch, "wcd": wcd, "csbs": csbs, "acdf": acdf}



class EstoqueMetricas:
    def __init__(self) -> None:
        self.estados: dict[str, EstadoMetricas] = {}

    def get_or_create(self, method_id: str) -> EstadoMetricas:
        if method_id not in self.estados:
            self.estados[method_id] = EstadoMetricas()
        return self.estados[method_id]
    
    




def get_tags_repositorio() -> list[str]:
    result = subprocess.run(
        ['git', '-C', './repo1', 'tag', '--sort=creatordate'],
        capture_output=True,
        text=True
        )
    tags = result.stdout.splitlines()
    return tags


def gerar_relatorio_repositorio():

    print("Lista de tags de repositório (em ordem cronológica antiga -> nova):")
    tags = get_tags_repositorio()
    contagem_tags = len(tags)
    print(tags) #imprime todas as tags para facilitar a seleção depois pelo usuário
    
    # print('5 primeiras tags')
    # for t in tags[:5]:
    #     print(t)

    # print('...')
    
    # print('5 últimas tags')
    # for t in tags[-5:]:
    #     print(t)


    print("-"*50)
    print(f'Foram encontradas {contagem_tags} tags no repositório')
    result = subprocess.run(['git', '-C', './repo1', 'rev-list', '--count', '--all'], capture_output=True, text=True)
    contagem_total_commits = result.stdout.splitlines()
    print(f'Foram encontrados {contagem_total_commits} Commits no repositório')
    print("-"*50)


def coletar_commits_entre_tags(atual, proxima):
    lista_commits = []
    try:
        commits_result = subprocess.run(['git', '-C', './repo1', 'rev-list', f'{atual}..{proxima}'], capture_output=True, text=True, check=True)
        lista_commits = commits_result.stdout
        print(lista_commits)
        quantidade_commits = len(commits_result.stdout.splitlines())
        print(f"Foram encontrados {quantidade_commits} commits entre as tags {atual} e {proxima}")
        return lista_commits.splitlines()


    except Exception as e:
        print(e)
        print("O programa falhou devido a um erro no git checkout durante a tag " + atual)
        print("Tente limpar as mudanças no repositório git antes de tentar de novo, Execute: 'git reset' ou apague manualmente no vscode")
    return lista_commits

def obter_lista_arquivos_java_por_commit():
    repo = Path("./repo1")
    lista_arquivos_java = list(repo.rglob('*.java'))
    return lista_arquivos_java
    

def listar_arquivos_java_commit(hash_commit: str) -> list[str]:
    try:
        result = subprocess.run(
            ['git', '-C', './repo1', 'ls-tree', '-r', '--name-only', hash_commit],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as e:
        print(e)
        print("Falha ao listar arquivos Java do commit " + hash_commit)
        return []
    return [line for line in result.stdout.splitlines() if line.endswith(".java")]


def resultado_dir_para_arquivo(commit: str, rel_path: str) -> Path:
    rel = Path("repo1") / rel_path
    if rel.suffix == ".java":
        rel = rel.with_suffix("")
    return Path("results") / commit / rel


def commit_ja_coletado(hash_commit: str) -> bool:
    output_dir = Path("results") / hash_commit
    if not output_dir.is_dir():
        return False

    java_files = listar_arquivos_java_commit(hash_commit)
    if not java_files:
        return False

    for rel_path in java_files:
        metodo_dir = resultado_dir_para_arquivo(hash_commit, rel_path)
        if not metodo_dir.is_dir():
            return False
        if not any(metodo_dir.rglob("*.java")):
            return False
    return True


def commit_tem_resultados(hash_commit: str) -> bool:
    output_dir = Path("results") / hash_commit
    if not output_dir.is_dir():
        return False
    return any(output_dir.rglob("*.java"))


def resultados_ja_coletados(lista_commits: list[str]) -> bool:
    return all(commit_tem_resultados(commit) for commit in lista_commits)


def listar_java_modificados(prev_commit: str, curr_commit: str) -> tuple[set[str], set[str]]:
    modificados: set[str] = set()
    removidos: set[str] = set()
    try:
        result = subprocess.run(
            ['git', '-C', './repo1', 'diff', '--name-status', '-M', prev_commit, curr_commit],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception as e:
        print(e)
        print("Falha ao listar arquivos modificados entre " + prev_commit + " e " + curr_commit)
        return modificados, removidos

    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            if len(parts) >= 3:
                old_path = parts[1]
                new_path = parts[2]
                if old_path.endswith(".java"):
                    removidos.add(old_path)
                if new_path.endswith(".java"):
                    modificados.add(new_path)
            continue

        if len(parts) < 2:
            continue
        path = parts[1]
        if not path.endswith(".java"):
            continue
        if status.startswith("D"):
            removidos.add(path)
        else:
            modificados.add(path)

    return modificados, removidos


def remover_resultado_arquivo(commit: str, rel_path: str) -> None:
    metodo_dir = resultado_dir_para_arquivo(commit, rel_path)
    if metodo_dir.is_dir():
        shutil.rmtree(metodo_dir)


def fazer_checkout_commit(hash_commit: str) -> bool:
    try:
        print("Realizando checkout do commit " + hash_commit)
        result = subprocess.run(
            ['git', '-C', './repo1', 'checkout', hash_commit],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(result.stderr.strip() or result.stdout.strip())
            print("O programa falhou devido a um erro no git checkout durante o commit " + hash_commit)
            print("Veja se o commit existe e tente novamente")
            return False
    except Exception as e:
        print(e)
        print("O programa falhou devido a um erro no git checkout durante o commit " + hash_commit)
        print("Veja se o commit existe e tente novamente")
        return False
    return True


def extrair_metodos_de_arquivos(hash_commit: str, arquivos: list[Path]) -> None:
    for arquivo in arquivos:
        print("Extraindo métodos do arquivo " + str(arquivo))
        try:
            result = subprocess.run(
                ['java', '-jar', 'JMethodsExtractor-0.0.1-SNAPSHOT-jar-with-dependencies.jar', 'file', arquivo, hash_commit],
                capture_output=True,
                text=True,
            ) # adicionei a extensão .java agora para ele achar o caminho, pois se deixar a extensão no caminho do arquivo na lista ele quebra na hora de fazer o diff
            if result.returncode != 0:
                erro = result.stderr.strip() or result.stdout.strip() or "erro desconhecido"
                registrar_erro_jar(
                    "Erro no jar | commit=" + hash_commit + " | arquivo=" + str(arquivo) + " | erro=" + erro
                )
        except Exception as e:
            registrar_erro_jar(
                "Erro no jar | commit=" + hash_commit + " | arquivo=" + str(arquivo) + " | erro=" + str(e)
            )
            print("Erro durante extração com jar " + str(e))


def extrair_method_files_incremental(prev_commit: str, curr_commit: str) -> None:
    if commit_ja_coletado(curr_commit):
        print("Pasta ja coletada para o commit " + curr_commit + ". Pulando extracao.")
        return

    prev_dir = Path("results") / prev_commit
    if not prev_dir.is_dir():
        print("Resultados anteriores nao encontrados. Fazendo extracao completa do commit " + curr_commit)
        extrair_method_files_commit(curr_commit)
        return

    curr_dir = Path("results") / curr_commit
    if curr_dir.exists():
        shutil.rmtree(curr_dir)
    shutil.copytree(prev_dir, curr_dir)

    modificados, removidos = listar_java_modificados(prev_commit, curr_commit)
    for rel_path in removidos:
        remover_resultado_arquivo(curr_commit, rel_path)
    for rel_path in modificados:
        remover_resultado_arquivo(curr_commit, rel_path)

    if not modificados:
        return
    if not fazer_checkout_commit(curr_commit):
        return
    arquivos = [Path("repo1") / rel_path for rel_path in sorted(modificados)]
    extrair_metodos_de_arquivos(curr_commit, arquivos)


def extrair_method_files_commit(hash_commit): #arrumar o hash_commit
    if commit_ja_coletado(hash_commit):
        print("Pasta ja coletada para o commit " + hash_commit + ". Pulando extracao.")
        return
    if not fazer_checkout_commit(hash_commit):
        return

    print("Iniciando extração do commit " + hash_commit)
    lista_arquivos_java = obter_lista_arquivos_java_por_commit()
    #lista_arquivos_java = lista_arquivos_java[:100]
    extrair_metodos_de_arquivos(hash_commit, lista_arquivos_java)

def preparar_ambiente(link_repositorio):
    header = ['project', 'commit', 'commitprevious', 'release', 'file', 'method', 'BOM', 'TACH', 'FCH', 'LCH',
                      'CHO', 'FRCH', 'CHD', 'WCH', 'WCD', 'WFR', 'ATAF', 'LCA', 'LCD', 'CSB', 'CSBS', 'ACDF']
    if not isdir("results"):
        os.mkdir("results")

    if not isdir('repo1'):
        subprocess.run(['git', 'clone', link_repositorio, 'repo1'])
    
    f = open("./results/evometrics.csv", "a")
    writer = csv.writer(f)
    writer.writerow(header)
    
    return writer


def registrar_erro_jar(mensagem: str) -> None:
    log_path = Path("results") / "erros_jar.log"
    try:
        with log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(mensagem + "\n")
    except Exception as e:
        print("Falha ao escrever log de erro: " + str(e))

def map_method_files_diretorio_commits(root_dir) -> dict[str, Path]:
    root = Path(root_dir)
    files : dict[str, Path] = {}
    for file in root.rglob("*.java"):
        rel = file.relative_to(root).as_posix()
        files[rel] = file
    return files

def fazer_diff_metodos_entre_commits(commit_atual, proximo_commit):
    metodos_commit_atual = map_method_files_diretorio_commits(f"results/{commit_atual}")
    metodos_proximo_commit = map_method_files_diretorio_commits(f"results/{proximo_commit}")
    atual_ids = set(metodos_commit_atual)
    proximo_ids = set(metodos_proximo_commit)

    metodos_novos = proximo_ids - atual_ids
    metodos_removidos = atual_ids - proximo_ids
    metodos_comuns = atual_ids & proximo_ids
    
    modificados = []
    for metodo in metodos_comuns:
        path_atual = metodos_commit_atual[metodo]
        proximo_path = metodos_proximo_commit[metodo]
        if not filecmp.cmp(path_atual, proximo_path, shallow=False):
            modificados.append(metodo)
        adicionadas, deletadas = contar_linhas_adicionadas_e_deletadas(path_atual, proximo_path)
        if adicionadas > 0 or deletadas > 0:
            print(f"Adicionadas: {adicionadas}   Deletadas: {deletadas} no método: {metodo}")

def contar_linhas_adicionadas_e_deletadas(path_atual, proximo_path):
    linhas_arq_atual = Path(path_atual).read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)
    linhas_prox_arquivo = Path(proximo_path).read_text(encoding='utf-8', errors='replace').splitlines(keepends=True)
    adicionadas = deletadas = 0
    for linha in difflib.ndiff(linhas_arq_atual, linhas_prox_arquivo):
        if linha.startswith("+ "):
            adicionadas += 1
        elif linha.startswith("- "):
            deletadas +=1
    return adicionadas, deletadas

def contar_loc(path):
    nloc = 0
    try:
        with open(path, 'r') as cmp:
            nloc = len(cmp.readlines())
    except:
        print('Erro lendo nloc: ' + path)
        print(sys.exc_info())
    return nloc

def parse_file_method(method_id: str) -> tuple[str, str]:
    p = Path(method_id)
    file_path = p.parent.as_posix()
    method_name = p.stem
    return file_path, method_name

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
                    prog='Assitende de mineração de métricas evolutivas',
                    description='Este programa auxilia na mineração de repositórios do github e na extração de métricas evolutivas a partir da análise das diferenças entres as tags/commits',
                    epilog='Texto na parte inferior da memsagem de ajuda')
    parser.add_argument('-l', '--link_github', required=True)
    parser.add_argument('--java', required=False)
    parser.add_argument('--incremental', action='store_true')


    args = parser.parse_args()
    link_repositorio = args.link_github

    # link_repositorio = 'https://github.com/eclipse-cdt/cdt.git' #args.link_github

    writer = preparar_ambiente(link_repositorio) #cria pasta e retorna e referência ao arquivo de evometrics

    project = link_repositorio.split("/")[-1].replace(".git", "")

    if args.java: print('o java escolhido é: ' + args.java)

    print("Gerando relatório inicial do repositório selecionado")
    gerar_relatorio_repositorio()

    coletar_intervalo = input("Deseja inserir um intervalo de tags para coleta? (S) Sim ; (N) Não (coletar todas): ").strip().lower()
    if(coletar_intervalo == "s"):
        lista_tags = input("Forneça as tags em formato de lista, \nex: ['CDT_9_0_0', 'CDT_9_0_1']\n Sua lista: ")
        lista_tags = ast.literal_eval(lista_tags)
        # lista_tags = ['CDT_9_0_0', 'CDT_9_0_1']
        print("Dica: copie da lista de tags impressa anteriormente")
        print(lista_tags)
    else:
        lista_tags = get_tags_repositorio()
    

    store = EstoqueMetricas()
    lista_commits: list[str] = []
    
    for prev_tag, curr_tag in zip(lista_tags, lista_tags[1:]):
        lista_commits.extend(coletar_commits_entre_tags(prev_tag, curr_tag))

    seen = set()
    lista_commits = [c for c in lista_commits if not (c in seen or seen.add(c))] # ? evitar que commits não lineares sejam processados mais de uma vez
    
    lista_commits = lista_commits[::-1] #inversão da lista para ele ficar em ordem cronológica

    if resultados_ja_coletados(lista_commits):
        print("Resultados ja coletados para todos os commits. Pulando extracao de metodos.")
    else:
        if args.incremental:
            commit0 = lista_commits[0]
            extrair_method_files_commit(commit0)
            for prev_commit, curr_commit in zip(lista_commits, lista_commits[1:]):
                extrair_method_files_incremental(prev_commit, curr_commit)
        else:
            for commit in lista_commits:
                extrair_method_files_commit(commit)

    commit0 = lista_commits[0]

    print("Coletando dados iniciais do primeiro commit")
    # setup inicial (release 1)
    methods = map_method_files_diretorio_commits(f'results/{commit0}') #usado para fazer o setup inicial do estado interno que servirá como referência
    for method_id, path in methods.items():
        state = store.get_or_create(method_id)
        nloc_birth = contar_loc(path)
        state.on_seen(release=1, nloc=nloc_birth)

        # escrever CSV com TACH=0, CHO=0, etc
        file_path, method_name = parse_file_method(method_id)
        row = [
            project, commit0, "", 1, file_path, method_name,
            state.bom, 0, state.fch, state.lch, 0, state.frch, 0,
            0, 0, state.wfr, 0, state.lca, state.lcd, state.csb, 0, 0
        ]
        writer.writerow(row)

    # commits seguintes
    for release, (prev, curr) in enumerate(zip(lista_commits, lista_commits[1:]), start=2):
        print("Coletando dados iniciais do commit" + str(release))
        prev_map = map_method_files_diretorio_commits(f"results/{prev}")
        curr_map = map_method_files_diretorio_commits(f"results/{curr}")

        novos = curr_map.keys() - prev_map.keys()
        comuns = curr_map.keys() & prev_map.keys()

        # novos -> BOM
        for method_id in novos:
            state = store.get_or_create(method_id)
            nloc_birth = contar_loc(curr_map[method_id])
            state.on_seen(release, nloc_birth)

        # comuns -> diff
        for method_id in comuns:
            state = store.get_or_create(method_id)
            prev_path = prev_map[method_id]
            curr_path = curr_map[method_id]

            if not filecmp.cmp(prev_path, curr_path, shallow=False):
                added, deleted = contar_linhas_adicionadas_e_deletadas(prev_path, curr_path)
                tach = added + deleted
                loc_current = contar_loc(curr_path)
                state.on_change(release, tach, loc_current)
                cho = 1
            else:
                tach = 0
                cho = 0

            metrics = state.finalize_release(release)
            ataf = tach / state.frch if state.frch > 0 else 0

            # escrever CSV usando metrics + tach + cho
            file_path, method_name = parse_file_method(method_id)
            chd = (tach / loc_current) if tach > 0 and loc_current > 0 else 0.0
            state.wfr += (release - 1) * cho

            row = [
                project, curr, prev, release, file_path, method_name,
                state.bom, tach, state.fch, state.lch, cho, state.frch, chd,
                metrics["wch"], metrics["wcd"], state.wfr, ataf,
                state.lca, state.lcd, state.csb, metrics["csbs"], metrics["acdf"]
            ]
            writer.writerow(row)