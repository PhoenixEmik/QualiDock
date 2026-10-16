import test from "node:test";
import assert from "node:assert/strict";
import { evidenceDocuments } from "../src/demultiplex.ts";

test("Illumina upload preserves original UTF-8/BOM/CRLF bytes and restricts document names", async () => {
  const bytes = new Uint8Array([
    239,
    187,
    191,
    ...new TextEncoder().encode("[Data]\r\nSample_ID,index\r\nA,ACGT\r\n"),
  ]);
  const file = new File([bytes], "SampleSheet.csv");
  const [actual] = await evidenceDocuments([file]);
  assert.deepEqual(
    Buffer.from(actual.content_base64, "base64"),
    Buffer.from(bytes),
  );
  await assert.rejects(
    evidenceDocuments([new File(["arbitrary"], "../../SampleSheet.csv")]),
  );
  await assert.rejects(evidenceDocuments([file, file]));
});
