`isWeekend` プラグインを追加しました。`dayjs().isWeekend()` は土曜・日曜なら `true`、平日なら `false` を返します。

新しいテストは `TZ=UTC` と `TZ=Asia/Tokyo` の両方で通りました。`TZ=UTC` でのフルスイート（798件）も通り、新プラグインの行カバレッジは 100% です。lint も問題ありません。

**追加したファイル**
- `src/plugin/isWeekend/index.js`：本体です。`this.day()` の値が 0（日曜）か 6（土曜）かを判定します。
- `types/plugin/isWeekend.d.ts`：型定義です。`interface Dayjs` に `isWeekend(): boolean` を追加しました。
- `test/plugin/isWeekend.test.js`：テストです。土日、平日5日分、ロケールで週の始まりを月曜にした場合、UTC モードの日付境界を確認しています。

**動作について**
- ロケールの週の始まりの設定には左右されません。
- UTC モードでは、UTC 基準の曜日で判定します。

```js
import isWeekend from 'dayjs/plugin/isWeekend'
dayjs.extend(isWeekend)
dayjs('2024-01-06').isWeekend() // true（土曜）
```

コミットはまだしていません。必要なら `feat(plugin): add isWeekend plugin` などのメッセージでコミットします。
