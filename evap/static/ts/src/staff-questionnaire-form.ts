import { assertDefined, selectOrError } from "./utils.js";

export class StaffQuestionnaireForm {
    private readonly questionTable: HTMLTableElement;
    private readonly questionnaireTypeSelect: HTMLSelectElement | null;

    constructor(questionTableId: string) {
        this.questionTable = selectOrError<HTMLTableElement>(`#${questionTableId}`);
        this.questionnaireTypeSelect = document.querySelector<HTMLSelectElement>('select[name="type"]');
    }

    private selectChangedHandler = (e: Event): void => {
        const target = e.currentTarget as HTMLSelectElement;
        const questionTypeCell = target.closest("td.question-type");
        if (!questionTypeCell) return;
        
        const checkboxes = questionTypeCell.querySelectorAll("input[type=checkbox]");
        
        // Do not do anything if the value is not set to enable saving
        // if (target.value === undefined || target.value === "") {
        //     return;
        // }
        
        if (target.value === "0" || target.value === "5") {  // 0: Text question; 5: Heading
            checkboxes.forEach(checkbox => {
                const checkboxElement = checkbox as HTMLInputElement;
                checkboxElement.checked = false;
                checkboxElement.disabled = true;
            });
        } else {
            // Check if this is a dropout questionnaire before enabling checkboxes
            if (this.questionnaireTypeSelect) {
                const questionnaireType = parseInt(this.questionnaireTypeSelect.value);
                
                if (questionnaireType === 5) { // Dropout questionnaire
                    checkboxes.forEach(checkbox => {
                        const checkboxElement = checkbox as HTMLInputElement;
                        if (checkboxElement.classList.contains('counts-for-grade-checkbox')) {
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
        
        const selectedType = parseInt(this.questionnaireTypeSelect.value);
        const countsForGradeCheckboxes = document.querySelectorAll('.counts-for-grade-checkbox');
        
        if (selectedType === 5) { // Dropout questionnaire
            countsForGradeCheckboxes.forEach(checkbox => {
                const checkboxElement = checkbox as HTMLInputElement;
                const questionTypeCell = checkboxElement.closest("td.question-type");
                assertDefined(questionTypeCell);
                
                const questionTypeSelect = selectOrError<HTMLSelectElement>("select", questionTypeCell);
                
                // Skip empty template forms to prevent Django validation issues
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
                
                // Skip empty template forms to prevent Django validation issues
                if (questionTypeSelect.value === "") {
                    return;
                }
                
                const questionType = parseInt(questionTypeSelect.value);
                if (questionType === 0 || questionType === 5) { // 0: Text question; 5: Heading
                    checkboxElement.checked = false;
                    checkboxElement.disabled = true;
                } else {
                    checkboxElement.disabled = false;
                }
            });
        }
    };

    public registerSelectChangedHandlers = (): void => {
        document.querySelectorAll(".question-type select").forEach(selectElement => {
            selectElement.addEventListener('change', this.selectChangedHandler);
            // selectElement.dispatchEvent(new Event('change'));
        });
        
        if (this.questionnaireTypeSelect) {
            this.questionnaireTypeSelect.addEventListener('change', this.handleQuestionnaireTypeChange);
        }
    };
}
