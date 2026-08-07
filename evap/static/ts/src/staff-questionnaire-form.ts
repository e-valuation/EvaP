import { saneParseInt, selectOrError } from "./utils.js";

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
        this.handleQuestionnaireTypeChange();
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

    private setAvailable = (checkbox: HTMLInputElement, available: boolean) => {
        if (available) {
            this.enableAndInit(checkbox, true);
        } else {
            this.disableAndUncheck(checkbox);
        }
    };

    private updateCheckboxes = (questionTypeCell: Element) => {
        const questionTypeSelect = selectOrError<HTMLSelectElement>("select", questionTypeCell);
        if (questionTypeSelect.value === "") {
            return;
        }

        const questionType = saneParseInt(questionTypeSelect.value);
        const questionnaireType = saneParseInt(this.questionnaireTypeSelect.value);
        const isRatingQuestion = questionType !== QUESTION_TYPE_TEXT && questionType !== QUESTION_TYPE_HEADING;
        const isDropoutQuestionnaire = questionnaireType === QUESTIONNAIRE_TYPE_DROPOUT;

        const textanswerCheckbox = selectOrError<HTMLInputElement>(".allow-textanswer-checkbox", questionTypeCell);
        const countsForGradeCheckbox = selectOrError<HTMLInputElement>(".counts-for-grade-checkbox", questionTypeCell);

        this.setAvailable(textanswerCheckbox, isRatingQuestion);
        this.setAvailable(countsForGradeCheckbox, isRatingQuestion && !isDropoutQuestionnaire);
    };

    private handleQuestionTypeChange = (e: Event) => {
        const target = e.target as HTMLElement;
        const questionTypeCell = target.closest("td.question-type");
        if (!questionTypeCell || !target.matches("select")) {
            return;
        }

        this.updateCheckboxes(questionTypeCell);
    };

    private handleQuestionnaireTypeChange = () => {
        for (const questionTypeCell of this.questionTable.querySelectorAll("td.question-type")) {
            this.updateCheckboxes(questionTypeCell);
        }
    };
}
