/**
Derived from https://github.com/simsalabim/sisyphus, originally distributed under the following license:

---------------------------------------------- begin original license
Copyright (c) 2011-2013 Alexander Kaupanin https://github.com/simsalabim

Permission is hereby granted, free of charge, to any person obtaining
a copy of this software and associated documentation files (the
"Software"), to deal in the Software without restriction, including
without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to
permit persons to whom the Software is furnished to do so, subject to
the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
---------------------------------------------- end original license

New portions and modifications are licensed under the conditions in LICENSE.md
 */

import { assert } from "./utils.js";

interface AutoFormSaverOptions {
    href: string;
    customKeySuffix: string;
    onSave: (arg0: AutoFormSaver) => void;
    onRestore: (arg0: AutoFormSaver) => void;
}

interface ValueElement extends Element {
    value: string | string[] | boolean;
}

export class AutoFormSaver {
    private options: AutoFormSaverOptions;

    constructor(
        private readonly target: HTMLFormElement,
        options: Partial<AutoFormSaverOptions>,
    ) {
        const defaults: AutoFormSaverOptions = {
            customKeySuffix: "",
            href: location.hostname + location.pathname,
            onSave: function () {},
            onRestore: function () {},
        };

        this.options = { ...defaults, ...options };

        this.restoreAllData();

        this.bindSaveData();
    }

    findFieldsToProtect(): ValueElement[] {
        return Array.of(...this.target.elements).filter((el: Element): el is ValueElement => {
            if (
                el instanceof HTMLInputElement &&
                ["submit", "reset", "button", "file", "password", "hidden"].includes(el.type.toLowerCase())
            ) {
                return false;
            }
            if (["BUTTON", "FIELDSET", "OBJECT", "OUTPUT"].includes(el.tagName)) {
                return false;
            }
            assert("value" in el);
            assert(typeof el.value === "string" || Array.isArray(el.value) || typeof el.value === "boolean");
            return true;
        });
    }

    getPrefix(field: Element) {
        return (
            this.options.href +
            this.target.id +
            this.target.name +
            (field.getAttribute("name") ?? "") +
            this.options.customKeySuffix
        );
    }

    bindSaveData() {
        for (const field of this.findFieldsToProtect()) {
            const prefix = this.getPrefix(field);
            if ((field instanceof HTMLInputElement && field.type === "text") || field instanceof HTMLTextAreaElement) {
                this.bindSaveDataImmediately(field, prefix);
            }
            this.bindSaveDataOnChange(field);
        }
    }

    saveAllData() {
        for (const field of this.findFieldsToProtect()) {
            if (!field.getAttribute("name")) {
                continue;
            }
            const prefix = this.getPrefix(field);
            const fieldType = field.getAttribute("type");
            let value = field.value;

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
        if (!field.hasAttribute("name")) {
            return false;
        }
        if (field instanceof HTMLInputElement && field.type === "checkbox") {
            field.checked = storedValue === "true";
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

    saveToBrowserStorage(key: string, value: any, fireCallback = true) {
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
            localStorage.removeItem(this.getPrefix(field));
        }
    }
}
