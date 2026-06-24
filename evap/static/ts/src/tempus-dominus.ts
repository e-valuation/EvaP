declare global {
    interface Window {
        tempusDominus: any;
    }
}

const td = window.tempusDominus ?? (globalThis as any).tempusDominus;

export const tempusDominus = td;
