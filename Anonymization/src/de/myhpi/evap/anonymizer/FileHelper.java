package de.myhpi.evap.anonymizer;

import java.io.BufferedReader;
import java.io.FileReader;
import java.io.FileWriter;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;

public class FileHelper {
    public static List<String> readLinesFromFile(String filename) throws IOException {
        List<String> lines = new ArrayList<String>();
        BufferedReader reader = new BufferedReader(new FileReader(filename));
        String line;
        while ((line = reader.readLine()) != null) {
            if (!line.isEmpty()) {
                if (!lines.contains(line)) {
                    lines.add(line);
                }
            }
        }
        reader.close();
        return lines;
    }

    public static void writeToFile(String string, String outputFile) throws IOException {
        FileWriter writer = new FileWriter(outputFile);
        writer.write(string);
        writer.close();
    }
}
