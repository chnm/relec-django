/**
 * This is a minimal config.
 *
 * If you need the full config, get it from here:
 * https://unpkg.com/browse/tailwindcss@latest/stubs/defaultConfig.stub.js
 */

module.exports = {
  content: [
    /**
     * HTML. Paths to Django template files that will contain Tailwind CSS classes.
     */

    /*  Templates within theme app (<tailwind_app_name>/templates), e.g. base.html. */
    "../templates/**/*.html",

    /*
     * Main templates directory of the project (BASE_DIR/templates).
     * Adjust the following line to match your project structure.
     */
    "../../templates/**/*.html",

    /*
     * Templates in other django apps (BASE_DIR/<any_app_name>/templates).
     * Adjust the following line to match your project structure.
     */
    "../../**/templates/**/*.html",

    /**
     * JS: If you use Tailwind CSS in JavaScript, uncomment the following lines and make sure
     * patterns match your project structure.
     */
    /* JS 1: Ignore any JavaScript in node_modules folder. */
    // '!../../**/node_modules',
    /* JS 2: Process all JavaScript files in the project. */
    // '../../**/*.js',

    /**
     * Python: If you use Tailwind CSS classes in Python, uncomment the following line
     * and make sure the pattern below matches your project structure.
     */
    // '../../**/*.py'
  ],
  theme: {
    extend: {
      // Custom color palette matching Religious Ecologies site
      colors: {
        // Primary brand colors (Religious Ecologies blue palette)
        'primary': {
          50: '#eff8ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#0060b1', // Main brand color
          700: '#004d91', // Darker variation
          800: '#003d73',
          900: '#002d55',
        },

        // Religious Ecologies specific colors
        'religious': {
          'primary': '#0060b1',    // Main blue for navigation and links
          'secondary': '#3b82f6',  // Lighter blue for accents
          'accent': '#f59e0b',     // Warm amber for highlights
          'muted': '#6b7280',      // Gray for muted text
        },

        // Extended grays for better content hierarchy
        'content': {
          'primary': '#111827',    // Very dark gray for main text
          'secondary': '#374151',  // Medium gray for secondary text
          'tertiary': '#6b7280',   // Light gray for labels
          'quaternary': '#9ca3af', // Very light gray for placeholders
        },

        // Background variants
        'surface': {
          'primary': '#ffffff',    // Pure white
          'secondary': '#f9fafb',  // Very light gray (current bg-gray-50)
          'tertiary': '#f3f4f6',   // Light gray for cards
          'accent': '#fef3c7',     // Light amber for highlights
        },

        // Semantic colors for data visualization
        'data': {
          'blue': '#3b82f6',
          'emerald': '#10b981',
          'amber': '#f59e0b',
          'red': '#ef4444',
          'purple': '#8b5cf6',
          'teal': '#14b8a6',
          'orange': '#f97316',
          'pink': '#ec4899',
        },
      },

      // Typography system with custom Google Fonts
      fontFamily: {
        'heading': ['Cormorant', 'ui-serif', 'Georgia', 'serif'], // For headlines
        'body': ['Quattrocento', 'ui-serif', 'Georgia', 'serif'], // For body text
        'serif': ['Quattrocento', 'ui-serif', 'Georgia', 'serif'], // Default serif
        'sans': ['ui-sans-serif', 'system-ui', 'sans-serif', 'Apple Color Emoji', 'Segoe UI Emoji', 'Segoe UI Symbol', 'Noto Color Emoji'],
        'mono': ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'Liberation Mono', 'Courier New', 'monospace'],
      },

      // Extended spacing for academic layouts
      spacing: {
        '18': '4.5rem',
        '88': '22rem',
        '128': '32rem',
      },

      // Custom shadows for depth
      boxShadow: {
        'religious': '0 4px 6px -1px rgba(0, 96, 177, 0.1), 0 2px 4px -1px rgba(0, 96, 177, 0.06)',
        'religious-lg': '0 10px 15px -3px rgba(0, 96, 177, 0.1), 0 4px 6px -2px rgba(0, 96, 177, 0.05)',
      },

      // Custom border radius
      borderRadius: {
        'xl': '0.75rem',
        '2xl': '1rem',
        '3xl': '1.5rem',
      },

      // Animation for interactive elements
      animation: {
        'fade-in': 'fadeIn 0.3s ease-in-out',
        'slide-in': 'slideIn 0.3s ease-in-out',
      },

      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideIn: {
          '0%': { transform: 'translateY(-10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [
    /**
     * '@tailwindcss/forms' is the forms plugin that provides a minimal styling
     * for forms. If you don't like it or have own styling for forms,
     * comment the line below to disable '@tailwindcss/forms'.
     */
    require("@tailwindcss/forms"),
    require("@tailwindcss/typography"),
    require("@tailwindcss/aspect-ratio"),
  ],
};
