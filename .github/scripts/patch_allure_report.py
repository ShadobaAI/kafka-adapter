#!/usr/bin/env python3
import argparse
from pathlib import Path


TIME_FORMAT_SCRIPT = """<script data-kafka-adapter-time-format>
(() => {
  const nativeDateTimeFormat = Intl.DateTimeFormat;
  if (nativeDateTimeFormat.__kafkaAdapterPatched) {
    return;
  }

  function patchedDateTimeFormat(locales, options) {
    if (options && (options.hour || options.minute || options.second || options.timeStyle)) {
      options = { ...options, hour12: false, hourCycle: "h23" };
    }
    return new nativeDateTimeFormat(locales, options);
  }

  Object.setPrototypeOf(patchedDateTimeFormat, nativeDateTimeFormat);
  patchedDateTimeFormat.prototype = nativeDateTimeFormat.prototype;
  patchedDateTimeFormat.supportedLocalesOf = nativeDateTimeFormat.supportedLocalesOf.bind(nativeDateTimeFormat);
  patchedDateTimeFormat.__kafkaAdapterPatched = true;
  Intl.DateTimeFormat = patchedDateTimeFormat;
})();
</script>"""


def patch_index(report_dir):
    index_path = report_dir / "index.html"
    content = index_path.read_text(encoding="utf-8")
    marker = "data-kafka-adapter-time-format"
    if marker in content:
        return

    if "<head>" not in content:
        raise RuntimeError(f"Не найден тег <head> в {index_path}")

    content = content.replace("<head>", f"<head>\n{TIME_FORMAT_SCRIPT}", 1)
    index_path.write_text(content, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-dir", required=True)
    args = parser.parse_args()
    patch_index(Path(args.report_dir))


if __name__ == "__main__":
    main()
