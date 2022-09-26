import { testable } from "src/text-answer-warnings";

test("normalize converts to lower case", () => {
    expect(testable.normalize("This is MY comment")).toBe("this is my comment");
});

test.each([
    ["two  spaces", "two spaces"],
    ["three   spaces", "three spaces"],
    ["a\ttab", "a tab"],
    ["a\nnewline", "a newline"],
    ["multiple   places\t\t\tto\n\n\nreplace", "multiple places to replace"],
])("normalize whitespaces from %j to %j", (text, expected) => {
    expect(testable.normalize(text)).toBe(expected);
});

test("normalize trims", () => {
    expect(testable.normalize("  surrounded by whitespaces\n")).toBe("surrounded by whitespaces");
});

test.each(["/", "-", "?", "n/A", "k.A.", "-/-", "none."])("detect as meaningless: %j", text => {
    const normalized = testable.normalize(text);
    expect(testable.isTextMeaningless(normalized)).toBe(true);
});

test.each([
    "",
    "c",
    "word",
    "Kanone",
    "I didn't understand the definition of n/A",
    "The abbreviation k.A. is known to me, but maybe not to all",
])("do not detect as meaningless: %j", text => {
    const normalized = testable.normalize(text);
    expect(testable.isTextMeaningless(normalized)).toBe(false);
});
