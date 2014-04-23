package de.myhpi.evap.anonymizer.users;

public class Person {
    private String firstname;
    private String lastname;
    private String username;

    public Person(String firstname, String lastname) {
        this.firstname = firstname;
        this.lastname = lastname;
        this.username = firstname.toLowerCase() + "." + lastname.toLowerCase();
    }

    public String getFirstname() {
        return firstname;
    }

    public String getLastname() {
        return lastname;
    }

    public String getUsername() {
        return username;
    }

    public String getUsernameExternal() {
        return username + ".ext";
    }

    public String getHPIStudentEmail() {
        return username + "@student.hpi.uni-potsdam.de";
    }

    public String getHPIStaffEmail() {
        return username + "@hpi.uni-potsdam.de";
    }

    public String getExternalEmail() {
        return username + "@myhpi.de";
    }

    @Override
    public boolean equals(Object other) {
        if (other instanceof Person) {
            return username.equals(((Person) other).getUsername());
        }
        return false;
    }

    @Override
    public int hashCode() {
        return username.hashCode()*3+1;
    }
}
