// Independent reference for SeqKit 2.14's fixed-size reservoir selection.
// Run with standard Go; production and automated tests do not require Go.
package main
import ("encoding/json"; "math/rand"; "os"; "sort")
func main() {
    results := []map[string]interface{}{}
    for _, seed := range []int64{73, 74} {
        for _, count := range []int{1, 7} {
            random := rand.New(rand.NewSource(seed))
            indices := make([]int, count)
            for i := range indices { indices[i] = i }
            for i := count; i < 400; i++ {
                j := random.Int63n(int64(i+1))
                if j < int64(count) { indices[j] = i }
            }
            sort.Ints(indices)
            results = append(results, map[string]interface{}{"population":400,"count":count,"seed":seed,"indices":indices})
        }
    }
    json.NewEncoder(os.Stdout).Encode(results)
}
