import { assert, selectOrError } from "./utils.js";

export const setupTomSelectCount = () => {
    document.querySelectorAll("[data-track-tomselect-count]").forEach(trackerElement => {
        assert(trackerElement instanceof HTMLElement);
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-type-assertion
        const trackedElement = (selectOrError(trackerElement.dataset.trackTomselectCount!) as any).tomselect;

        update_count(trackerElement, trackedElement);
        trackedElement.on("item_add", function () {
            update_count(trackerElement, trackedElement);
        });
        trackedElement.on("item_remove", function () {
            update_count(trackerElement, trackedElement);
        });
        function update_count(trackerElement: any, trackedElement: any) {
            trackerElement.innerText = trackedElement.items.length;
        }
    });
};
