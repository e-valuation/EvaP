package de.myhpi.evap.anonymizer.courses;

public class Course {
    private int id;
    private String name_de;
    private String name_en;

    public Course(int id, String name_de, String name_en) {
        this.id = id;
        this.name_de = name_de;
        this.name_en = name_en;
    }
    
    public int getId() {
        return id;
    }
    
    public String getName_de() {
        return name_de;
    }
    
    public String getName_en() {
        return name_en;
    }
}
