const I18N = {
    currentLocale: 'fr',
    translations: {},

    async loadLocale(locale) {
        if (this.translations[locale]) {
            this.currentLocale = locale;
            return;
        }
        try {
            const res = await fetch(`/static/i18n/${locale}.json`);
            if (res.ok) {
                this.translations[locale] = await res.json();
                this.currentLocale = locale;
            } else {
                console.warn(`i18n: ${locale} not found, keeping ${this.currentLocale}`);
            }
        } catch (e) {
            console.warn(`i18n: load error for ${locale}, keeping ${this.currentLocale}`);
        }
    },

    t(key, params = {}) {
        const keys = key.split('.');
        let val = this.translations[this.currentLocale];
        for (const k of keys) {
            val = val?.[k];
        }
        if (typeof val !== 'string') return key;
        return val.replace(/\{(\w+)\}/g, (_, k) => params[k] ?? `{${k}}`);
    }
};
