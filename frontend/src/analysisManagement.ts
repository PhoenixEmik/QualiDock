import type { Run } from "./types";
export function filteredAnalyses(
  runs: Run[],
  search: string,
  state: string,
  mode: string,
  order: string,
) {
  return runs
    .filter((run) => {
      const status =
        state === "all" ||
        (state === "active"
          ? ["queued", "running"].includes(run.state)
          : state === "issues"
            ? ["partial", "failed", "interrupted"].includes(run.state)
            : run.state === state);
      return (
        status &&
        (mode === "all" || run.mode === mode) &&
        `${run.name} ${run.id}`
          .toLocaleLowerCase()
          .includes(search.trim().toLocaleLowerCase())
      );
    })
    .sort((a, b) => {
      const field = order.startsWith("finished") ? "finished_at" : "created_at";
      const left = a[field],
        right = b[field];
      if (!left || !right)
        return left === right ? a.id.localeCompare(b.id) : !left ? 1 : -1;
      const delta = left.localeCompare(right);
      return (
        (order.endsWith("asc") ? delta : -delta) || a.id.localeCompare(b.id)
      );
    });
}
