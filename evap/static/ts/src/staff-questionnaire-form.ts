import { assertDefined, saneParseInt, selectOrError } from "./utils.js";

const QUESTION_TYPE_TEXT = 0;
const QUESTION_TYPE_HEADING = 5;
const QUESTIONNAIRE_TYPE_DROPOUT = 5;

export class StaffQuestionnaireForm {
    private readonly questionnaireTypeSelect: HTMLSelectElement;

    constructor(
        private readonly questionTable: HTMLTableElement,
        form: HTMLFormElement,
    ) {
        this.questionnaireTypeSelect = selectOrError<HTMLSelectElement>("[data-questionnaire-type-select]", form);
    }

    public attach = (): void => {
        this.questionTable.addEventListener("change", this.handleQuestionTypeChange);
        this.questionnaireTypeSelect.addEventListener("change", this.handleQuestionnaireTypeChange);

        // initialize the state of all checkboxes based on current question types and questionnaire type
        const questionTypeSelects = this.questionTable.querySelectorAll<HTMLSelectElement>("td.question-type select");
        questionTypeSelects.forEach(select => {
            select.dispatchEvent(new Event("change", { bubbles: true }));
        });
    };
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

    private handleQuestionTypeChange = (e: Event) => {
        const target = e.target as HTMLElement;
        const questionTypeCell = target.closest("td.question-type");
        if (!questionTypeCell || !target.matches("select")) {
            return;
        }

        const questionTypeSelect = target;
        if (questionTypeSelect.value === "") {
            return;
        }

        const questionType = saneParseInt(questionTypeSelect.value);
        const questionnaireType = saneParseInt(this.questionnaireTypeSelect.value);

        for (const checkbox of questionTypeCell.querySelectorAll<HTMLInputElement>("input[type=checkbox]")) {
            const shouldDisableFromQuestion = questionType === QUESTION_TYPE_TEXT || questionType === QUESTION_TYPE_HEADING;
            const shouldDisableFromQuestionnaire = checkbox.classList.contains("counts-for-grade-checkbox") && questionnaireType == QUESTIONNAIRE_TYPE_DROPOUT;

            if (shouldDisableFromQuestion || shouldDisableFromQuestionnaire) {
                this.disableAndUncheck(checkbox);
            } else {
                this.enableAndInit(checkbox, true);
            }
        };
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

}
