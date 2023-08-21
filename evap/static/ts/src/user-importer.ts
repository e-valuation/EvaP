import { selectOrError } from "./utils.js";
import { CSRF_HEADERS } from "./csrf-utils.js";

export function attachFormSubmitDownloadAndRedirect(form_id: string, filename: string, redirectUrl: string) {
    let form: HTMLFormElement = selectOrError("#" + form_id);
    let formData = new FormData(form);
    form.onsubmit = _ => {
        fetch(form.action, {
            method: form.method,
            headers: CSRF_HEADERS,
            body: formData,
        })
            .then(resp => resp.blob())
            .then(blob => {
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement("a");
                a.style.display = "none";
                a.href = url;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                window.location.href = redirectUrl; //redirect
            })
            .catch(reason => alert(reason));
        return false; // stop event propagation
    };
}
