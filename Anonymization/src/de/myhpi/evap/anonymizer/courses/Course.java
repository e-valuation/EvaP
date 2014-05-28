package de.myhpi.evap.anonymizer.courses;

public class Course {
    private int id;
    private int semester;
    private String degree;
    private String name_de;
    private String name_en;

    public Course(int id, int semester, String degree, String name_de, String name_en) {
        this.id = id;
        this.semester = semester;
        this.degree = degree;
        this.name_de = name_de;
        this.name_en = name_en;
    }

    public int getId() {
        return id;
    }

    public int getSemester() {
        return semester;
    }

    public String getDegree() {
        return degree;
    }

    public String getName_de() {
        return name_de;
    }

    public String getName_en() {
        return name_en;
    }
}
