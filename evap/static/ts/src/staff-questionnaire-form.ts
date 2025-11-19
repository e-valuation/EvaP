import { assertDefined, saneParseInt, selectOrError } from "./utils.js";

const QUESTION_TYPE_TEXT = 0;
const QUESTION_TYPE_HEADING = 5;
const QUESTIONNAIRE_TYPE_DROPOUT = 5;

export class StaffQuestionnaireForm {
    private readonly questionTable: HTMLTableElement;
    private readonly questionnaireTypeSelect: HTMLSelectElement;

    constructor(questionTable: HTMLTableElement) {
        this.questionTable = questionTable;
        this.questionnaireTypeSelect = selectOrError<HTMLSelectElement>("#id_type");
        this.initialize();
    }
    private disableAndUncheckCheckbox = (checkbox: HTMLInputElement) => {
        checkbox.checked = false;
        checkbox.disabled = true;
    };

    private enableAndCheckCheckbox = (checkbox: HTMLInputElement) => {
        checkbox.checked = true;
        checkbox.disabled = false;
    };

    private disableAllCheckboxes = (checkboxes: NodeListOf<Element>) => {
        checkboxes.forEach(checkbox => {
            this.disableAndUncheckCheckbox(checkbox as HTMLInputElement);
        });
    };

    private enableAllCheckboxes = (checkboxes: NodeListOf<Element>) => {
        checkboxes.forEach(checkbox => {
            this.enableAndCheckCheckbox(checkbox as HTMLInputElement);
        });
    };

    private handleQuestionTypeChange = (e: Event) => {
        const target = e.currentTarget as HTMLSelectElement;
        const questionType = saneParseInt(target.value);
        const questionTypeCell = target.closest("td.question-type");
        if (!questionTypeCell) return;

        const checkboxes = questionTypeCell.querySelectorAll("input[type=checkbox]");

        if (questionType === QUESTION_TYPE_TEXT || questionType === QUESTION_TYPE_HEADING) {
            this.disableAllCheckboxes(checkboxes);
            return;
        }

        const questionnaireType = saneParseInt(this.questionnaireTypeSelect.value);
        if (questionnaireType === QUESTIONNAIRE_TYPE_DROPOUT) {
            checkboxes.forEach(checkbox => {
                const checkboxElement = checkbox as HTMLInputElement;
                if (checkboxElement.classList.contains("counts-for-grade-checkbox")) {
                    this.disableAndUncheckCheckbox(checkboxElement);
                } else {
                    this.enableAndCheckCheckbox(checkboxElement);
                }
            });
        } else {
            this.enableAllCheckboxes(checkboxes);
        }
    };

    private handleQuestionnaireTypeChange = () => {
        const selectedType = saneParseInt(this.questionnaireTypeSelect.value);
        const countsForGradeCheckboxes = document.querySelectorAll(".counts-for-grade-checkbox");

        if (selectedType === QUESTIONNAIRE_TYPE_DROPOUT) {
            countsForGradeCheckboxes.forEach(checkbox => {
                const checkboxElement = checkbox as HTMLInputElement;
                const questionTypeCell = checkboxElement.closest("td.question-type");
                assertDefined(questionTypeCell);

                const questionTypeSelect = selectOrError<HTMLSelectElement>("select", questionTypeCell);

                if (questionTypeSelect.value === "") {
                    return;
                }

                this.disableAndUncheckCheckbox(checkboxElement);
            });
        } else {
            countsForGradeCheckboxes.forEach(checkbox => {
                const checkboxElement = checkbox as HTMLInputElement;
                const questionTypeCell = checkboxElement.closest("td.question-type");
                assertDefined(questionTypeCell);

                const questionTypeSelect = selectOrError<HTMLSelectElement>("select", questionTypeCell);

                if (questionTypeSelect.value === "") {
                    return;
                }

                const questionType = saneParseInt(questionTypeSelect.value);
                if (questionType === QUESTION_TYPE_TEXT || questionType === QUESTION_TYPE_HEADING) {
                    this.disableAndUncheckCheckbox(checkboxElement);
                } else {
                    this.enableAndCheckCheckbox(checkboxElement);
                }
            });
        }
    };

    private initialize = () => {
        // Initialize the state of all checkboxes based on current question types and questionnaire type
        const questionnaireType = saneParseInt(this.questionnaireTypeSelect.value);

        // Iterate through all question rows
        document.querySelectorAll(".question-type").forEach(questionTypeCell => {
            const questionTypeSelect = selectOrError<HTMLSelectElement>("select", questionTypeCell);
            const questionType = saneParseInt(questionTypeSelect.value);

            // Skip if no question type selected
            if (questionTypeSelect.value === "") {
                return;
            }

            const checkboxes = questionTypeCell.querySelectorAll("input[type=checkbox]");

            if (questionType === QUESTION_TYPE_TEXT || questionType === QUESTION_TYPE_HEADING) {
                checkboxes.forEach(checkbox => {
                    const checkboxElement = checkbox as HTMLInputElement;
                    checkboxElement.disabled = true;
                });
            }

            if (questionnaireType === QUESTIONNAIRE_TYPE_DROPOUT) {
                checkboxes.forEach(checkbox => {
                    const checkboxElement = checkbox as HTMLInputElement;
                    if (checkboxElement.classList.contains("counts-for-grade-checkbox")) {
                        checkboxElement.disabled = true;
                    }
                });
            }
        });
    };

    public registerSelectChangedHandlers = () => {
        document.querySelectorAll(".question-type select").forEach(selectElement => {
            selectElement.addEventListener("change", this.handleQuestionTypeChange);
        });

        this.questionnaireTypeSelect.addEventListener("change", this.handleQuestionnaireTypeChange);
    };
}
