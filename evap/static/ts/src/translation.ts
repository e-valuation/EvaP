export {};
declare global {
    interface Window {
        gettext(msgid: string): string;
        pluralidx(n: number | boolean): number;
        ngettext(singular: string, plural: string, count: number): string;
        gettext_noop(msgid: string): string;
        pgettext(context: string, msgid: string): string;
        npgettext(context: string, singular: string, plural: string, count: number): string;
        interpolate(fmt: string, obj: any, named: boolean): string;
        get_format(format_type: string): string;
    }
}
