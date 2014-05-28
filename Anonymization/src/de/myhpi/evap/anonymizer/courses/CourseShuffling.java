package de.myhpi.evap.anonymizer.courses;

import java.io.IOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Properties;

import de.myhpi.evap.anonymizer.FileHelper;

public class CourseShuffling {
    public static void shuffle(Properties properties, Connection connection)
            throws SQLException, IOException {
        System.out.println("Shuffling courses");

        String table = properties.getProperty("db_course_table");

        List<Course> courses = readCoursesFromDB(table, connection);
        List<Course> shuffledCourses = new ArrayList<Course>(courses);
        Collections.shuffle(shuffledCourses);

        String outputFile = properties.getProperty("output_courses");
        substituteCourses(courses, shuffledCourses, table, outputFile, connection);

        System.out.println("Courses shuffled, results written to " + outputFile);
    }

    private static List<Course> readCoursesFromDB(String table, Connection connection)
            throws SQLException {
        List<Course> courses = new ArrayList<Course>();
        Statement statement = connection.createStatement();
        statement.execute("SELECT id, semester_id, degree, name_de, name_en FROM " + table);
        ResultSet resultSet = statement.getResultSet();
        while (resultSet.next()) {
            int id = resultSet.getInt("id");
            int semester = resultSet.getInt("semester_id");
            String degree = resultSet.getString("degree");
            String name_de = resultSet.getString("name_de");
            String name_en = resultSet.getString("name_en");
            courses.add(new Course(id, semester, degree, name_de, name_en));
        }
        return courses;
    }

    private static void substituteCourses(List<Course> courses,
            List<Course> shuffledCourses, String table,
            String outputFile, Connection connection) throws IOException, SQLException {
        PreparedStatement preparedStatement = connection.prepareStatement(
                "UPDATE " + table + " " +
                "SET semester_id = ?, degree = ?, name_de = ?, name_en = ? " +
                "WHERE id = ?");

        StringBuffer changes = new StringBuffer();

        for (int i=0; i<courses.size(); i++) {
            Course original = courses.get(i);
            Course substitute = shuffledCourses.get(i);
            changes.append(original.getId())
                    .append(" => ")
                    .append(substitute.getId())
                    .append("\n");
            preparedStatement.setInt(5, original.getId());
            preparedStatement.setInt(1, substitute.getSemester());
            preparedStatement.setString(2, substitute.getDegree());
            preparedStatement.setString(3, substitute.getName_de() + " "); //add a space to avoid name collisions
            preparedStatement.setString(4, substitute.getName_en() + " ");
            preparedStatement.executeUpdate();
        }

        //remove the space again
        Statement statement = connection.createStatement();
        statement.execute("UPDATE " + table + 
                         " SET name_de=LEFT(name_de, char_length(name_de)-1)" +
                         " , name_en=LEFT(name_en, char_length(name_en)-1)" );

        FileHelper.writeToFile(changes.toString(), outputFile);
    }
}
