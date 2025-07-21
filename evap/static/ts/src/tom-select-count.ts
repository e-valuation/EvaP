


export const setupTomSelectCount = () => {
    document.querySelectorAll("[data-track-tomselect-count]").forEach(trackerElement => {
        let trackedElement = (document.getElementById((trackerElement as any).dataset.trackTomselectCount) as any).tomselect;
        trackedElement.on("item_add", function() {
            update_count(trackerElement, trackedElement);
        });
        trackedElement.on("item_remove", function() {
            update_count(trackerElement, trackedElement);
        });
        function update_count(trackerElement: any, trackedElement: any) {
            trackerElement.innerText = trackedElement.items.length;
        }
    });
}