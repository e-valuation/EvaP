package de.myhpi.evap.anonymizer.users;

public class User {
	private String username;
	private String email;
	
	public User(String username, String email) {
		this.username = username;
		this.email = email;
	}
	
	public String getUsername() {
		return username;
	}
	
	public boolean isHPIStudent() {
		return email.contains("@student.hpi.uni-potsdam.de");
	}
	
	public boolean isHPIStaff() {
		return email.contains("@hpi.uni-potsdam.de");
	}
}
