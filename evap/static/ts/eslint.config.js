// @ts-check

import eslint from "@eslint/js";
import tseslint from "typescript-eslint";

export default tseslint.config(
    eslint.configs.recommended,
    ...tseslint.configs.strictTypeChecked,
    ...tseslint.configs.stylisticTypeChecked,
    {
        ignores: ["rendered/", "eslint.config.js"],
    },
    {
        languageOptions: {
            ecmaVersion: 5,
            parserOptions: {
                project: ["tsconfig.json", "tsconfig.compile.json"],
            },
            sourceType: "module",
        },
    },
    // ignore @typescript-eslint/no-misused-promises
    {
        rules: {
            "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
            "no-else-return": "error",
            // not fixed in this PR
            "@typescript-eslint/no-misused-promises": "off",
            "@typescript-eslint/no-namespace": "off",
            "@typescript-eslint/no-non-null-assertion": "off",
            "@typescript-eslint/no-unsafe-call": "off",
            "@typescript-eslint/no-unsafe-member-access": "off",
            "@typescript-eslint/no-unsafe-argument": "off",
            "@typescript-eslint/no-unsafe-assignment": "off",
            "@typescript-eslint/no-explicit-any": "off",
            "@typescript-eslint/no-empty-function": "off",
            "@typescript-eslint/no-unnecessary-type-parameters": "off",
            // fixed in this PR
            "@typescript-eslint/no-unused-vars": [
                "warn",
                {
                    args: "all",
                    argsIgnorePattern: "^_",
                    caughtErrors: "all",
                    caughtErrorsIgnorePattern: "^_",
                    destructuredArrayIgnorePattern: "^_",
                    varsIgnorePattern: "^_",
                    ignoreRestSiblings: true,
                },
            ],
            "@typescript-eslint/no-confusing-void-expression": "warn",
            "@typescript-eslint/no-floating-promises": "warn",
            "@typescript-eslint/no-unsafe-return": "warn",
            "@typescript-eslint/no-redundant-type-constituents": "warn",
        },
    },
);
