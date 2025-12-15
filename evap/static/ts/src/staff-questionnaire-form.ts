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

        this.questionTable.addEventListener("change", this.handleQuestionTypeChange);
        this.questionnaireTypeSelect.addEventListener("change", this.handleQuestionnaireTypeChange);

        this.initialize();
    }
    private disableAndUncheck = (checkbox: HTMLInputElement) => {
        checkbox.checked = false;
        checkbox.disabled = true;
    };

    private enableAndCheck = (checkbox: HTMLInputElement) => {
        checkbox.checked = true;
        checkbox.disabled = false;
    };

    private disableAll = (checkboxes: NodeListOf<Element>) => {
        checkboxes.forEach(checkbox => {
            this.disableAndUncheck(checkbox as HTMLInputElement);
        });
    };

    private enableAll = (checkboxes: NodeListOf<Element>) => {
        checkboxes.forEach(checkbox => {
            this.enableAndCheck(checkbox as HTMLInputElement);
        });
    };

    private handleQuestionTypeChange = (e: Event) => {
        const target = e.target as HTMLElement;
        const questionTypeCell = target.closest("td.question-type");
        if (questionTypeCell && target.matches("select")) {
            const questionTypeSelect = target as HTMLSelectElement;
            const questionType = saneParseInt(questionTypeSelect.value);

            const checkboxes = questionTypeCell.querySelectorAll("input[type=checkbox]");

            if (questionType === QUESTION_TYPE_TEXT || questionType === QUESTION_TYPE_HEADING) {
                this.disableAll(checkboxes);
                return;
            }

            const questionnaireType = saneParseInt(this.questionnaireTypeSelect.value);
            if (questionnaireType === QUESTIONNAIRE_TYPE_DROPOUT) {
                checkboxes.forEach(checkbox => {
                    const checkboxElement = checkbox as HTMLInputElement;
                    if (checkboxElement.classList.contains("counts-for-grade-checkbox")) {
                        this.disableAndUncheck(checkboxElement);
                    } else {
                        this.enableAndCheck(checkboxElement);
                    }
                });
            } else {
                this.enableAll(checkboxes);
            }
        }
    };

    private handleQuestionnaireTypeChange = () => {
        const selectedType = saneParseInt(this.questionnaireTypeSelect.value);
        const countsForGradeCheckboxes = document.querySelectorAll(".counts-for-grade-checkbox");

        countsForGradeCheckboxes.forEach(checkbox => {
            const checkboxElement = checkbox as HTMLInputElement;
            const questionTypeCell = checkboxElement.closest("td.question-type");
            assertDefined(questionTypeCell);

            const questionTypeSelect = selectOrError<HTMLSelectElement>("select", questionTypeCell);

            if (questionTypeSelect.value === "") {
                return;
            }

            if (selectedType === QUESTIONNAIRE_TYPE_DROPOUT) {
                this.disableAndUncheck(checkboxElement);
            } else {
                const questionType = saneParseInt(questionTypeSelect.value);
                if (questionType === QUESTION_TYPE_TEXT || questionType === QUESTION_TYPE_HEADING) {
                    this.disableAndUncheck(checkboxElement);
                } else {
                    this.enableAndCheck(checkboxElement);
                }
            }
        });
    };

    private initialize = () => {
        // Initialize the state of all checkboxes based on current question types and questionnaire type
        const questionnaireType = saneParseInt(this.questionnaireTypeSelect.value);

        document.querySelectorAll(".question-type").forEach(questionTypeCell => {
            const questionTypeSelect = selectOrError<HTMLSelectElement>("select", questionTypeCell);
            const questionType = saneParseInt(questionTypeSelect.value);

            if (questionTypeSelect.value === "") {
                return;
            }

            const checkboxes = questionTypeCell.querySelectorAll("input[type=checkbox]");
            const isTextOrHeading = questionType === QUESTION_TYPE_TEXT || questionType === QUESTION_TYPE_HEADING;

            checkboxes.forEach(checkbox => {
                const checkboxElement = checkbox as HTMLInputElement;
                const isCountsForGrade = checkboxElement.classList.contains("counts-for-grade-checkbox");

                if (isTextOrHeading || (questionnaireType === QUESTIONNAIRE_TYPE_DROPOUT && isCountsForGrade)) {
                    checkboxElement.disabled = true;
                }
            });
        });
    };
}
