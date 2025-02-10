/**
 * Plugin for saving form data to local storage to restore them later.
 *
 * Based on Sisyphus by Alexander Kaupanin <kaupanin@gmail.com>
 */

interface AutoFormSaverOptions {
    name?: string;
    excludeFields: string[];
    customKeySuffix: string;
    onSave: (arg0: AutoFormSaver) => void;
    onRestore: (arg0: AutoFormSaver) => void;
}

export class AutoFormSaver {
    private options: AutoFormSaverOptions;
    private readonly href: string;
    private readonly target: HTMLFormElement;

    constructor(target: HTMLFormElement, options: AutoFormSaverOptions) {
        const defaults = {
            excludeFields: [],
            customKeySuffix: "",
            timeout: 0,
            onSave: function () {},
            onRestore: function () {},
        };

        this.options = { ...defaults, ...options };

        this.target = target;
        if (this.options.name) {
            this.href = this.options.name;
        } else {
            this.href = location.hostname + location.pathname;
        }

        this.restoreAllData();

        this.bindSaveData();
    }

    findFieldsToProtect(): Element[] {
        return Array.of(...this.target.elements).filter((el: Element) => {
            if (
                el instanceof HTMLInputElement &&
                ["submit", "reset", "button", "file", "password", "hidden"].includes(el.type.toLowerCase())
            ) {
                return false;
            }
            if (["BUTTON", "FIELDSET", "OBJECT", "OUTPUT"].includes(el.tagName)) {
                return false;
            }
            return true;
        });
    }

    getExcludeFields(): Element[] {
        return this.options.excludeFields.flatMap(selector => Array.from(document.querySelectorAll(selector)));
    }

    getPrefix(field: Element) {
        return (
            this.href +
            this.target.id +
            this.target.name +
            (field.getAttribute("name") ?? "") +
            this.options.customKeySuffix
        );
    }

    bindSaveData() {
        for (const field of this.findFieldsToProtect()) {
            if (this.getExcludeFields().includes(field)) {
                continue;
            }
            const prefix = this.getPrefix(field);
            if ((field instanceof HTMLInputElement && field.type === "text") || field instanceof HTMLTextAreaElement) {
                this.bindSaveDataImmediately(field, prefix);
            }
            this.bindSaveDataOnChange(field);
        }
    }

    saveAllData() {
        for (const field of this.findFieldsToProtect()) {
            if (this.getExcludeFields().includes(field) || !field.getAttribute("name")) {
                continue;
            }
            const prefix = this.getPrefix(field);
            const fieldType = field.getAttribute("type");
            // @ts-expect-error All field objects are some kind of input field with value.
            let value: string | string[] | boolean = field.value;

            if (field instanceof HTMLInputElement && fieldType === "checkbox") {
                value = field.checked;
                this.saveToBrowserStorage(prefix, value, false);
            } else if (field instanceof HTMLInputElement && fieldType === "radio") {
                if (field.checked) {
                    value = field.value;
                    this.saveToBrowserStorage(prefix, value, false);
                }
            } else {
                this.saveToBrowserStorage(prefix, value, false);
            }
        }
        this.options.onSave(this);
    }

    restoreAllData() {
        let restored = false;

        for (const field of this.findFieldsToProtect()) {
            if (this.getExcludeFields().includes(field)) {
                continue;
            }
            const storedValue = localStorage.getItem(this.getPrefix(field));
            if (storedValue !== null) {
                this.restoreFieldsData(field, storedValue);
                restored = true;
            }
        }

        if (restored) {
            this.options.onRestore(this);
        }
    }

    restoreFieldsData(field: Element, storedValue: string) {
        if (field.getAttribute("name") === undefined) {
            return false;
        }
        if (field instanceof HTMLInputElement && field.type === "checkbox") {
            field.checked = storedValue !== "false";
        } else if (field instanceof HTMLInputElement && field.type === "radio") {
            if (field.value === storedValue) {
                field.checked = true;
            }
        } else {
            // @ts-expect-error Definitely an input field with a value, but not known by type
            field.value = storedValue;
        }
    }

    bindSaveDataImmediately(field: HTMLInputElement | HTMLTextAreaElement, prefix: string) {
        field.addEventListener("input", () => {
            this.saveToBrowserStorage(prefix, field.value);
        });
    }

    saveToBrowserStorage(key: string, value: any, fireCallback?: boolean) {
        // if fireCallback is undefined it should be true
        fireCallback = fireCallback ?? true;
        // eslint-disable-next-line @typescript-eslint/restrict-plus-operands
        localStorage.setItem(key, value + "");
        if (fireCallback && value !== "") {
            this.options.onSave(this);
        }
    }

    bindSaveDataOnChange(field: Element) {
        field.addEventListener("change", () => {
            this.saveAllData();
        });
    }

    releaseData() {
        for (const field of this.findFieldsToProtect()) {
            if (this.getExcludeFields().includes(field)) {
                continue;
            }
            localStorage.removeItem(this.getPrefix(field));
        }
    }
}
