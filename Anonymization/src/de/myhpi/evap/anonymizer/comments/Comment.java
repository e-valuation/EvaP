package de.myhpi.evap.anonymizer.comments;

public class Comment {
    private int id;
    private String reviewed_answer;
    private String original_answer;

    public Comment(int id, String reviewed_answer, String original_answer) {
        this.id = id;
        this.reviewed_answer = reviewed_answer;
        this.original_answer = original_answer;
    }

    public int getId() {
        return id;
    }

    public String getReviewed_answer() {
        return reviewed_answer;
    }

    public String getOriginal_answer() {
        return original_answer;
    }
}
