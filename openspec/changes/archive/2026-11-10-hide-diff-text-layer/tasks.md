## 1. Фронтенд: убрать текст с diff-слоя

- [x] 1.1 В `static/app.js` в функции `buildDiffWordsHtml` перестал вставлять текст слова (`w.word`) в HTML: для `DELETE` и `INSERT` рендерится пустой `<div class="diff-word delete/insert">` без текстового contenuto с сохранением координат `left/top/width/height`; для `EQUAL` элементы на diff-слое не рендерятся. Верификация: в сгенерированном HTML нет вставки `w.word`/`escaped` для ни одной операции.
- [x] 1.2 В `static/styles.css` из базового класса `.diff-word` убраны шрифтовые свойства (`font-size`, `font-family`, `color`, `line-height`), оставлены только позиционирование (`position: absolute`, `z-index`, `user-select`, `white-space`, `overflow`, `transform-origin`). Для `.diff-word.delete` / `.diff-word.insert` сохранены `background-color`, `border-radius`, `padding`. Верификация: `.diff-word` не содержит font-/color-свойств; подсветка остаётся цветным боксом.
- [x] 1.3 Селекторы `.diff-word.delete` / `.diff-word.insert` в `insertSpacersForOps` продолжают находить элементы (классы не менялись). Верификация: поиск `.querySelectorAll('.diff-word.delete')` / `.querySelectorAll('.diff-word.insert')` возвращает элементы после применения diff.

## 2. Тесты

- [x] 2.1 Добавлен тест: `EQUAL`-слова не попадают в `.diff-layer` как видимый текст (элементы для EQUAL не рендерятся). Верификация: тест проходит.
- [x] 2.2 Добавлен тест: `DELETE`/`INSERT` создают элементы с правильными классами (`diff-word delete` / `diff-word insert`), корректными координатами `left/top/width/height` и без текстового contenuto. Верификация: тест проходит.
- [x] 2.3 Запущен полный набор тестов (`pytest`) — всё зелёное, включая существующие тесты diff_engine, pdf_handler, main. Верификация: `pytest` завершается без ошибок (44 passed).
