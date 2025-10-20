import { assert, selectOrError } from "./utils.js";

export const setupTomSelectCount = () => {
    document.querySelectorAll("[data-track-tomselect-count]").forEach(trackerElement => {
        assert(trackerElement instanceof HTMLElement);
        const trackedElement = selectOrError<any>(trackerElement.dataset.trackTomselectCount!).tomselect;
        const update_count = () => {
            trackerElement.innerText = trackedElement.items.length;
        };
        update_count();
        trackedElement.on("item_add", update_count);
        trackedElement.on("item_remove", update_count);
    });
};
