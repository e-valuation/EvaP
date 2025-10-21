import { assertDefined, saneParseInt, selectOrError } from "./utils.js";

const QUESTION_TYPE_TEXT = 0;
const QUESTION_TYPE_HEADING = 5;
const QUESTIONNAIRE_TYPE_DROPOUT = 5;

export class StaffQuestionnaireForm {
    private readonly questionTable: HTMLTableElement;
    private readonly questionnaireTypeSelect: HTMLSelectElement | null;

    constructor(questionTableId: string) {
        this.questionTable = selectOrError<HTMLTableElement>(`#${questionTableId}`);
        this.questionnaireTypeSelect = document.querySelector<HTMLSelectElement>('select[name="type"]');
    }

    private selectChangedHandler = (e: Event): void => {
        const target = e.currentTarget as HTMLSelectElement;
        const questionType = saneParseInt(target.value);
        const questionTypeCell = target.closest("td.question-type");
        if (!questionTypeCell) return;

        const checkboxes = questionTypeCell.querySelectorAll("input[type=checkbox]");

        if (questionType === QUESTION_TYPE_TEXT || questionType === QUESTION_TYPE_HEADING) {
            checkboxes.forEach(checkbox => {
                const checkboxElement = checkbox as HTMLInputElement;
                checkboxElement.checked = false;
                checkboxElement.disabled = true;
            });
        } else {
            // Check if this is a dropout questionnaire before enabling checkboxes
            if (this.questionnaireTypeSelect) {
                const questionnaireType = saneParseInt(this.questionnaireTypeSelect.value);

                if (questionnaireType === QUESTIONNAIRE_TYPE_DROPOUT) {
                    checkboxes.forEach(checkbox => {
                        const checkboxElement = checkbox as HTMLInputElement;
                        if (checkboxElement.classList.contains("counts-for-grade-checkbox")) {
                            checkboxElement.checked = false;
                            checkboxElement.disabled = true;
                        } else {
                            checkboxElement.checked = true;
                            checkboxElement.disabled = false;
                        }
                    });
                } else {
                    checkboxes.forEach(checkbox => {
                        const checkboxElement = checkbox as HTMLInputElement;
                        checkboxElement.checked = true;
                        checkboxElement.disabled = false;
                    });
                }
            } else {
                // Fallback: enable all checkboxes if questionnaire type not found
                checkboxes.forEach(checkbox => {
                    const checkboxElement = checkbox as HTMLInputElement;
                    checkboxElement.checked = true;
                    checkboxElement.disabled = false;
                });
            }
        }
    };

    private handleQuestionnaireTypeChange = (): void => {
        if (!this.questionnaireTypeSelect) return;

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

                checkboxElement.checked = false;
                checkboxElement.disabled = true;
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
                    checkboxElement.checked = false;
                    checkboxElement.disabled = true;
                } else {
                    checkboxElement.checked = true;
                    checkboxElement.disabled = false;
                }
            });
        }
    };

    public registerSelectChangedHandlers = (): void => {
        document.querySelectorAll(".question-type select").forEach(selectElement => {
            selectElement.addEventListener("change", this.selectChangedHandler);
            // selectElement.dispatchEvent(new Event('change'));
        });

        if (this.questionnaireTypeSelect) {
            this.questionnaireTypeSelect.addEventListener("change", this.handleQuestionnaireTypeChange);
        }
    };
}
