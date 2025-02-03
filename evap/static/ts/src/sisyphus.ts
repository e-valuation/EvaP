/**
 * Plugin developed to save html forms data to LocalStorage to restore them after browser crashes, tabs closings
 * and other disasters.
 *
 * @author Alexander Kaupanin <kaupanin@gmail.com>
 * @author Jonathan Weth <dev@jonathanweth.de>
 */

interface SisyphusOptions {
    name?: string;
    excludeFields: string[];
    customKeySuffix: string;
    locationBased: boolean;
    timeout: number;
    autoRelease: boolean;
    onSave: (arg0: Sisyphus) => void;
    onBeforeRestore: (arg0: Sisyphus) => boolean | undefined;
    onRestore: (arg0: Sisyphus) => void;
    onRelease: (arg0: Sisyphus) => void;
}

export class Sisyphus {
    private readonly identifier: string;
    private options: SisyphusOptions;
    private readonly href: string;
    private readonly targets: NodeListOf<HTMLFormElement>;

    constructor(identifier: string, options: SisyphusOptions) {
        const defaults = {
            excludeFields: [],
            customKeySuffix: "",
            locationBased: false,
            timeout: 0,
            autoRelease: true,
            onSave: function () {},
            onBeforeRestore: function () {},
            onRestore: function () {},
            onRelease: function () {},
        };

        this.identifier = identifier;
        this.options = { ...defaults, ...options };

        this.targets = document.querySelectorAll(this.identifier);
        if (this.options.name) {
            this.href = this.options.name;
        } else {
            this.href = location.hostname + location.pathname;
        }

        const callback_result = this.options.onBeforeRestore(this);
        if (callback_result === undefined || callback_result) {
            this.restoreAllData();
        }

        if (this.options.autoRelease) {
            this.bindReleaseData();
        }

        this.bindSaveData();
    }

    findFieldsToProtect(target: HTMLFormElement): Element[] {
        return Array.of(...target.elements).filter((el: Element) => {
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

    getFormIdAndName(target: HTMLFormElement) {
        return target.id + target.name;
    }

    getPrefix(target: HTMLFormElement, field: Element) {
        return (
            (this.options.locationBased ? this.href : "") +
            this.getFormIdAndName(target) +
            (field.getAttribute("name") ?? "") +
            this.options.customKeySuffix
        );
    }

    /**
     * Bind saving data
     */
    bindSaveData() {
        if (this.options.timeout) {
            this.saveDataByTimeout();
        }

        for (const target of this.targets) {
            for (const field of this.findFieldsToProtect(target)) {
                if (this.getExcludeFields().includes(field)) {
                    continue;
                }
                const prefix = this.getPrefix(target, field);
                if (
                    (field instanceof HTMLInputElement && field.type === "text") ||
                    field instanceof HTMLTextAreaElement
                ) {
                    if (!this.options.timeout) {
                        this.bindSaveDataImmediately(field, prefix);
                    }
                }
                this.bindSaveDataOnChange(field);
            }
        }
    }

    /**
     * Save all protected forms data to Local Storage.
     * Common method, necessary to not lead astray user firing 'data is saved' when select/checkbox/radio
     * is changed and saved, while text field data is saved only by timeout
     */
    saveAllData() {
        for (const target of this.targets) {
            const multiCheckboxCache: Record<string, boolean> = {};

            for (const field of this.findFieldsToProtect(target)) {
                if (this.getExcludeFields().includes(field) || !field.getAttribute("name")) {
                    continue;
                }
                const prefix = this.getPrefix(target, field);
                const fieldType = field.getAttribute("type");
                // @ts-expect-error All field objects are some kind of input field with value.
                let value: string | string[] | boolean = field.value;

                if (field instanceof HTMLInputElement && fieldType === "checkbox") {
                    if (field.name.includes("[")) {
                        if (multiCheckboxCache[field.name]) {
                            return;
                        }
                        const tempValue: string[] = [];
                        for(const partField of document.querySelectorAll("[name='" + field.name + "']:checked")) {
                            if (partField instanceof HTMLInputElement) {
                                                            tempValue.push(partField.value);
                            }
                        }
                        value = tempValue;
                        multiCheckboxCache[field.name] = true;
                    } else {
                        value = field.checked;
                    }
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
        }
        this.options.onSave(this);
    }

    /**
     * Restore forms data from Local Storage
     */
    restoreAllData() {
        let restored = false;

        for (const target of this.targets) {
            for (const field of this.findFieldsToProtect(target)) {
                if (this.getExcludeFields().includes(field)) {
                    continue;
                }
                const resque = localStorage.getItem(this.getPrefix(target, field));
                if (resque !== null) {
                    this.restoreFieldsData(field, resque);
                    restored = true;
                }
            }
        }

        if (restored) {
            this.options.onRestore(this);
        }
    }

    /**
     * Restore form field data from local storage
     */
    restoreFieldsData(field: Element, resque: string) {
        if (field.getAttribute("name") === undefined) {
            return false;
        }
        if (
            field instanceof HTMLInputElement &&
            field.type === "checkbox" &&
            resque !== "false" &&
            !field.name.includes("[")
        ) {
            field.checked = true;
        } else if (
            field instanceof HTMLInputElement &&
            field.type === "checkbox" &&
            resque === "false" &&
            !field.name.includes("[")
        ) {
            field.checked = false;
        } else if (field instanceof HTMLInputElement && field.type === "radio") {
            if (field.value === resque) {
                field.checked = true;
            }
        } else if (field instanceof HTMLInputElement && !field.name.includes("[")) {
            field.value = resque;
        } else {
            // @ts-expect-error Definitely an input field with a value, but not known by type
            field.value = resque.split(",");
        }
    }

    /**
     * Bind immediate saving (on typing/checking/changing) field data to local storage when user fills it
     */
    bindSaveDataImmediately(field: HTMLInputElement | HTMLTextAreaElement, prefix: string) {
        field.addEventListener("input", () => {
            this.saveToBrowserStorage(prefix, field.value);
        });
    }

    /**
     * Save data to Local Storage and fire callback if defined
     */
    saveToBrowserStorage(key: string, value: any, fireCallback?: boolean) {
        // if fireCallback is undefined it should be true
        fireCallback = fireCallback ?? true;
        // eslint-disable-next-line @typescript-eslint/restrict-plus-operands
        localStorage.setItem(key, value + "");
        if (fireCallback && value !== "") {
            this.options.onSave(this);
        }
    }

    /**
     * Bind saving field data on change
     */
    bindSaveDataOnChange(field: Element) {
        field.addEventListener("change", () => {
            this.saveAllData();
        });
    }

    /**
     * Saving (by timeout) field data to local storage when user fills it
     */
    saveDataByTimeout() {
        setTimeout(() => {
            const timeout = () => {
                this.saveAllData();
                setTimeout(timeout, this.options.timeout * 1000);
            };

            return timeout;
        }, this.options.timeout * 1000);
    }

    /**
     * Bind release form fields data from local storage on submit/reset form
     */
    bindReleaseData() {
        for (const target of this.targets) {
            const releaseHandler = () => {
                this.releaseData(target);
            };
            target.addEventListener("submit", releaseHandler);
            target.addEventListener("reset", releaseHandler);
        }
    }

    /**
     * Manually release form fields
     */
    manuallyReleaseData() {
        for (const target of this.targets) {
            this.releaseData(target);
        }
    }

    /**
     * Bind release form fields data from local storage on submit/resett form
     */
    releaseData(target: HTMLFormElement) {
        let released = false;

        for (const field of this.findFieldsToProtect(target)) {
            if (this.getExcludeFields().includes(field)) {
                continue;
            }
            localStorage.removeItem(this.getPrefix(target, field));
            released = true;
        }

        if (released) {
            this.options.onRelease(this);
        }
    }
}
