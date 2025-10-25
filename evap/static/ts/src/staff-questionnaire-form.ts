import { assertDefined, saneParseInt, selectOrError } from "./utils.js";

const QUESTION_TYPE_TEXT = 0;
const QUESTION_TYPE_HEADING = 5;
const QUESTIONNAIRE_TYPE_DROPOUT = 5;

export class StaffQuestionnaireForm {
    private readonly questionTable: HTMLTableElement;
    private readonly questionnaireTypeSelect: HTMLSelectElement;

    constructor(questionTableId: string) {
        this.questionTable = selectOrError<HTMLTableElement>(`#${questionTableId}`);
        this.questionnaireTypeSelect = selectOrError<HTMLSelectElement>('select[name="type"]');
    }
    private disableAndUncheckCheckbox = (checkbox: HTMLInputElement): void => {
        checkbox.checked = false;
        checkbox.disabled = true;
    };

    private enableAndCheckCheckbox = (checkbox: HTMLInputElement): void => {
        checkbox.checked = true;
        checkbox.disabled = false;
    };

    private disableAllCheckboxes = (checkboxes: NodeListOf<Element>): void => {
        checkboxes.forEach(checkbox => {
            this.disableAndUncheckCheckbox(checkbox as HTMLInputElement);
        });
    };

    private enableAllCheckboxes = (checkboxes: NodeListOf<Element>): void => {
        checkboxes.forEach(checkbox => {
            this.enableAndCheckCheckbox(checkbox as HTMLInputElement);
        });
    };

    private selectChangedHandler = (e: Event): void => {
        const target = e.currentTarget as HTMLSelectElement;
        const questionType = saneParseInt(target.value);
        const questionTypeCell = target.closest("td.question-type");
        if (!questionTypeCell) return;

        const checkboxes = questionTypeCell.querySelectorAll("input[type=checkbox]");

        if (questionType === QUESTION_TYPE_TEXT || questionType === QUESTION_TYPE_HEADING) {
            this.disableAllCheckboxes(checkboxes);
            return;
        }
        // Check if this is a dropout questionnaire before enabling checkboxes
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

    private handleQuestionnaireTypeChange = (): void => {
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

    public registerSelectChangedHandlers = (): void => {
        document.querySelectorAll(".question-type select").forEach(selectElement => {
            selectElement.addEventListener("change", this.selectChangedHandler);
        });

        this.questionnaireTypeSelect.addEventListener("change", this.handleQuestionnaireTypeChange);
    };
}
