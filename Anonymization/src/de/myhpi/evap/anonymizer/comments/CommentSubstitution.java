package de.myhpi.evap.anonymizer.comments;

import java.io.IOException;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;
import java.util.Properties;

import de.myhpi.evap.anonymizer.FileHelper;

public class CommentSubstitution {
	public static void substitute(Properties properties, Connection connection)
			throws IOException, SQLException {
		System.out.println("Substituting comments");
		
		String[] loremIpsum = getLoremIpsum(properties);
		
		String table = properties.getProperty("db_comment_table");
		List<Comment> comments = readCommentsFromDB(table, connection);
		
		substituteComments(loremIpsum, comments, table, connection);
		
		System.out.println("Comments substituted");
	}
	
	private static List<Comment> readCommentsFromDB(String table, Connection connection)
			throws SQLException {
		List<Comment> comments = new ArrayList<Comment>();
		Statement statement = connection.createStatement();
		statement.execute("SELECT id, reviewed_answer, original_answer FROM " + table);
		ResultSet resultSet = statement.getResultSet();
		while (resultSet.next()) {
			int id = resultSet.getInt("id");
			String reviewed_answer = resultSet.getString("reviewed_answer");
			String original_answer = resultSet.getString("original_answer");
			comments.add(new Comment(id, reviewed_answer, original_answer));
		}
		return comments;
	}

	private static String[] getLoremIpsum(Properties properties)
			throws IOException {
		String loremIpsumFile = properties.getProperty("input_lorem_ipsum");
		String loremIpsumRaw = FileHelper.readLinesFromFile(loremIpsumFile).get(0);
		return loremIpsumRaw.split(" ");
	}
	
	private static void substituteComments(String[] loremIpsum,
			List<Comment> comments, String table, Connection connection)
					throws SQLException {
		PreparedStatement preparedStatement = connection.prepareStatement(
				"UPDATE " + table + " " +
				"SET reviewed_answer = ?, original_answer = ? " +
				"WHERE id = ?");
		
		for (Comment comment : comments) {
			int id = comment.getId();
			String reviewed_answer = comment.getReviewed_answer();
			String original_answer = comment.getOriginal_answer();
			
			preparedStatement.setInt(3, id);
			preparedStatement.setString(1, getLoremIpsumSubstitution(loremIpsum, reviewed_answer));
			preparedStatement.setString(2, getLoremIpsumSubstitution(loremIpsum, original_answer));
			preparedStatement.executeUpdate();
		}
	}

	private static String getLoremIpsumSubstitution(String[] loremIpsum,
			String comment) {
		if (comment == null || comment.isEmpty()) {
			return null;
		}
		int length = comment.split(" ").length;
		return getLoremIpsumSubstitution(loremIpsum, length);
	}

	private static String getLoremIpsumSubstitution(String[] loremIpsum, int length) {
		StringBuffer buffer = new StringBuffer();
		for (int i=0, j=0; i < length; i++, j++) {
			if (j == loremIpsum.length) {
				j = 0;
			}
			buffer.append(loremIpsum[j]).append(" ");
		}
		return buffer.toString().trim();
	}
}
