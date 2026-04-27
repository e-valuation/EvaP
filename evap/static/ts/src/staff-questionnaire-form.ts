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

    private enableAndInit = (checkbox: HTMLInputElement, initialValue: boolean) => {
        // do not override current input user selection, if there is no need to
        if (checkbox.disabled) {
            checkbox.checked = initialValue;
        }
        checkbox.disabled = false;
    };

    private disableAndUncheckAll = (checkboxes: NodeListOf<Element>) => {
        checkboxes.forEach(checkbox => {
            this.disableAndUncheck(checkbox as HTMLInputElement);
        });
    };

    private enableAndInitAll = (checkboxes: NodeListOf<Element>, initialValue: boolean) => {
        checkboxes.forEach(checkbox => {
            this.enableAndInit(checkbox as HTMLInputElement, initialValue);
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
                this.disableAndUncheckAll(checkboxes);
                return;
            }

            const questionnaireType = saneParseInt(this.questionnaireTypeSelect.value);
            if (questionnaireType === QUESTIONNAIRE_TYPE_DROPOUT) {
                checkboxes.forEach(checkbox => {
                    const checkboxElement = checkbox as HTMLInputElement;
                    if (checkboxElement.classList.contains("counts-for-grade-checkbox")) {
                        this.disableAndUncheck(checkboxElement);
                    } else {
                        this.enableAndInit(checkboxElement, true);
                    }
                });
            } else {
                this.enableAndInitAll(checkboxes, true);
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
                    this.enableAndInit(checkboxElement, true);
                }
            }
        });
    };

    private initialize = () => {
        // Initialize the state of all checkboxes based on current question types and questionnaire type
        const questionTypeSelects = this.questionTable.querySelectorAll<HTMLSelectElement>("td.question-type select");

        questionTypeSelects.forEach(select => {
            select.dispatchEvent(new Event("change", { bubbles: true }));
        });
    };
}
