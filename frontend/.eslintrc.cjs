module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:react/recommended',
    'plugin:@typescript-eslint/recommended',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs'],
  parser: '@typescript-eslint/parser',
  plugins: ['react-refresh', '@typescript-eslint'],
  rules: {
    'react-refresh/only-export-components': [
      'warn',
      { allowConstantExport: true },
    ],
    'react/react-in-jsx-scope': 'off',
    // TypeScript enforces prop types at compile time; this rule can't see
    // through forwardRef<T, Props> generics and false-positives on them.
    'react/prop-types': 'off',
    // Loaded from eslint-local-rules/ via --rulesdir (see package.json lint script).
    // Warning only: 46 pre-existing violations across the codebase (AuthContext,
    // ChatWindow, APIKeyList, etc.) need fixing before this can gate CI as an error.
    'no-unguarded-setstate-after-await': 'warn',
  },
}
