declare const tempusDominus: {
    TempusDominus: new (
        element: Element,
        options?: object,
    ) => {
        show(): void;
        hide(): void;
    };
    DateTime: new () => { hour: number; minute: number; second: number };
};
