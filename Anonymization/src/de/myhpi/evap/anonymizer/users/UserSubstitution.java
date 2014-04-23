package de.myhpi.evap.anonymizer.users;

import java.io.IOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;
import java.util.Random;

import de.myhpi.evap.anonymizer.FileHelper;

public class UserSubstitution {
    public static final int NUMBER_OF_PERSONS = 2000;
    
    public static void substitute(Properties properties, Connection connection)
                    throws IOException, SQLException {
        System.out.println("Substituting users");
        
        String firstnamesFile = properties.getProperty("input_first_names");
        String lastnamesFile = properties.getProperty("input_last_names");
        String ignoreFile = properties.getProperty("input_ignores");
        String outputFile = properties.getProperty("output_users");
        String table = properties.getProperty("db_user_table");
        
        List<Person> persons = createPersons(firstnamesFile, lastnamesFile);
        List<User> users = readUsersFromDB(table, connection);
        List<String> ignores = FileHelper.readLinesFromFile(ignoreFile);

        substituteUsers(users, persons, ignores, table, connection, outputFile);
        
        System.out.println("Users substituted, results written to " + outputFile);
    }

    private static List<Person> createPersons(String firstnamesFile,
            String lastnamesFile) throws IOException {
        List<String> firstnames = FileHelper.readLinesFromFile(firstnamesFile);
        List<String> lastnames = FileHelper.readLinesFromFile(lastnamesFile);
        List<Person> persons = new ArrayList<Person>(NUMBER_OF_PERSONS);
        
        Random random = new Random(System.currentTimeMillis());
        while (persons.size() < NUMBER_OF_PERSONS) {
            int firstnameI = random.nextInt(firstnames.size());
            int lastnameI = random.nextInt(lastnames.size());
            Person person = new Person(firstnames.get(firstnameI), lastnames.get(lastnameI));
            if (!persons.contains(person)) {
                persons.add(person);
            }
        }
        return persons;
    }

    private static List<User> readUsersFromDB(String table, Connection connection)
            throws SQLException {
        List<User> users = new ArrayList<User>();
    
        Statement statement = connection.createStatement();
        statement.execute("SELECT username, email FROM " + table);
        ResultSet resultSet = statement.getResultSet();
        while (resultSet.next()) {
            String username = resultSet.getString("username");
            if (!username.isEmpty()) {
                String email = resultSet.getString("email");
                users.add(new User(username, email));
            }
        }
        
        return users;
    }

    private static void substituteUsers(List<User> users, List<Person> persons,
            List<String> ignores, String table, Connection connection,
            String outputFile)
                    throws IOException, SQLException {
        PreparedStatement preparedStatement = connection.prepareStatement(
                "UPDATE " + table + " " +
                "SET username = ?, first_name = ?, last_name = ?, email = ? " +
                "WHERE username = ?");
        
        StringBuffer changes = new StringBuffer();
        
        for (int i=0; i < users.size(); i++) {
            User user = users.get(i);
            if (!ignores.contains(user.getUsername().toLowerCase())) {
                Person person = persons.get(i);
                changes.append(user.getUsername())
                        .append(" => ")
                        .append(person.getUsername())
                        .append("\n");
                if (user.isHPIStaff() || user.isHPIStudent()) {
                    preparedStatement.setString(1, person.getUsername());
                } else {
                    preparedStatement.setString(1, person.getUsernameExternal());
                }
                preparedStatement.setString(2, person.getFirstname());
                preparedStatement.setString(3, person.getLastname());
                if (user.isHPIStaff()) {
                    preparedStatement.setString(4, person.getHPIStaffEmail());
                } else if (user.isHPIStudent()) {
                    preparedStatement.setString(4, person.getHPIStudentEmail());
                } else {
                    preparedStatement.setString(4, person.getExternalEmail());
                }
                preparedStatement.setString(5, user.getUsername());
                preparedStatement.executeUpdate();
            }
        }
        
        FileHelper.writeToFile(changes.toString(), outputFile);
    }
}
