// Which strings the macOS spell checker (NSSpellChecker, US English) accepts as words.
//
// Reads candidate strings from standard input, one per line, and prints, one per line and in the order read,
// each one the spell checker finds no misspelling in. A word the user taught the spell checker on this Mac
// ("Learn Spelling") is never printed, so the output does not depend on whose Mac it ran on.
//
// Part of the build of apps/api/app/memo/data/spelling_spellchecker_words.json, which
// app.memo.spelling folds into its list of real words that are never respelt. Run the build, not this file:
//
//     cd apps/api && PYTHONPATH=$PWD .venv/bin/python -m app.memo.spelling
//
// On its own: printf 'zines\nzimes\n' | swift scripts/spelling/spellchecker_accepts.swift   (prints "zines")

import AppKit

let checker = NSSpellChecker.shared
let language = "en_US"
var accepted: [String] = []
while let line = readLine(strippingNewline: true) {
    let word = line.trimmingCharacters(in: .whitespaces)
    if word.isEmpty || checker.hasLearnedWord(word) {
        continue
    }
    let miss = checker.checkSpelling(
        of: word, startingAt: 0, language: language, wrap: false, inSpellDocumentWithTag: 0, wordCount: nil
    )
    if miss.location == NSNotFound {
        accepted.append(word)
    }
}
print(accepted.joined(separator: "\n"))
