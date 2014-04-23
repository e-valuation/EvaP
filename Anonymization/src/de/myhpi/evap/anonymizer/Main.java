package de.myhpi.evap.anonymizer;

import java.io.FileReader;
import java.io.IOException;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.util.Properties;

import de.myhpi.evap.anonymizer.comments.CommentSubstitution;
import de.myhpi.evap.anonymizer.courses.CourseShuffling;
import de.myhpi.evap.anonymizer.users.UserSubstitution;

public class Main {
    public static void main(String[] args) throws IOException, ClassNotFoundException, SQLException {
        Properties properties = new Properties();
        properties.load(new FileReader(args[0]));
        
        Connection connection = connectToDB(properties);
        
        UserSubstitution.substitute(properties, connection);
        CourseShuffling.shuffle(properties, connection);
        CommentSubstitution.substitute(properties, connection);
        
        connection.close();
    }
    
    private static Connection connectToDB(Properties properties) throws ClassNotFoundException, SQLException {
        Class.forName("org.postgresql.Driver");
        String db_url = properties.getProperty("db_url");
        String db_user = properties.getProperty("db_user");
        String db_pw = properties.getProperty("db_password");
        return DriverManager.getConnection(db_url, db_user, db_pw);
    }
}