
import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileSystems;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.Collections;
import java.util.List;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.body.CallableDeclaration.Signature;
import com.github.javaparser.ast.body.MethodDeclaration;
import com.github.javaparser.resolution.TypeSolver;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;

public class Main {

	public static void main(String[] args)  {

		String mode = args[0];
		String projectOrFile = args[1];
		String output = args[2];
		
		File file = new File(projectOrFile);
		String fileSeparator = FileSystems.getDefault().getSeparator();
		String path = "results" + fileSeparator + output+ fileSeparator;
		if (mode.equals("project")) {
			try {
				searchFiles(projectOrFile, path, file);
			} catch (FileNotFoundException e) {
				// TODO Auto-generated catch block
				e.printStackTrace();
			}
			System.out.println("Finished methods extraction successfully...");
		} else if (mode.equals("file")) {
			try {
				extract_methods(path, file);
			} catch (FileNotFoundException e) {
				// TODO Auto-generated catch block
				e.printStackTrace();
			}
		} else {
			System.out.println("Attention: invalid mode, should be project of file!");
		}
	}

	private static void searchFiles(String dir, String path, File file) throws FileNotFoundException {
		TypeSolver typeSolver = new CombinedTypeSolver();
		JavaSymbolSolver symbolSolver = new JavaSymbolSolver(typeSolver);
		StaticJavaParser.getConfiguration().setSymbolResolver(symbolSolver);
		File[] tab = file.listFiles();
		if (tab != null) {
			for (File current : tab) {
//				System.out.println(current.getName());
				if (current.isFile()) {
					if (current.getName().endsWith(".java")) {
						extract_methods(path, current);
					}
				} else if (current.isDirectory()) {
					String fileSeparator = FileSystems.getDefault().getSeparator();
//					path += fileSeparator + current.getName();
//					dir += fileSeparator + current.getName();
					searchFiles(dir, path, current);
				}
			}
		} else {
			System.out.println("ATTENTION: cannot find directory : " + dir);
		}
	}

	private static void extract_methods(String path, File file) throws FileNotFoundException {
		CompilationUnit cu = StaticJavaParser.parse(new File(file.getPath()));
		cu.findAll(MethodDeclaration.class).forEach(ae -> {
			Signature sig = ae.getSignature();
			writeUsingFiles(path, file, sig.asString(), ae.toString());
		});
	}

	private static void writeUsingFiles(String path, File file, String filename, String data) {
    String filePath = file.getPath();
    if (filePath.endsWith(".java")) {
        filePath = filePath.substring(0, filePath.length() - 5);
    }
    
    // Monta o caminho de forma segura sem concatenar strings manualmente
    Path targetPath = Paths.get(path, filePath, filename + ".java");
    
    try {
        // Garante a criação de todos os diretórios pais necessários
        Files.createDirectories(targetPath.getParent());
        
        // Escreve os dados no arquivo de forma atômica e segura
        Files.write(targetPath, data.getBytes(StandardCharsets.UTF_8));
    } catch (IOException e) {
        e.printStackTrace();
    }
}
}