tailwind.config = {
    darkMode: 'class',
    theme: {
        extend: {
            colors: {
                // GNOME Adwaita-inspired dark palette
                surface: {
                    DEFAULT: '#0a0a0a',
                    secondary: '#141414',
                    card: '#171717',
                    raised: '#1f1f1f',
                },
                border: {
                    faint: '#2a2a2a',
                    muted: '#333333',
                    loud: '#404040',
                },
                // MedPrep accent colors
                heat: '#dc2626',
                amethyst: '#a07aff',
                bluetron: '#5a8ffc',
                crimson: '#f05545',
                forest: '#5cd47f',
                honey: '#f0c550',
                rose: '#e06c8a',
                teal: '#2dd4bf',
            },
            borderRadius: {
                'gnome': '16px',
                'gnome-sm': '12px',
                'gnome-lg': '24px',
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
            },
        },
    },
};
