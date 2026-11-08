"""Agreement between LLM-judge hard_fail and human UNACCEPTABLE labels (calibration of the judge)."""
import glob, json, sys
import yaml
human_file, tags = sys.argv[1], sys.argv[2:]
hum = yaml.safe_load(open(human_file))
for tag in tags:
    tp = fp = fn = tn = 0; fps = []
    for f in sorted(glob.glob(f"results/{tag}/*.json")):
        r = json.load(open(f))
        for i, j in enumerate(r["judge"]["candidates"][:3]):
            key = f"{r['case_id']}-{i+1}"
            h = hum.get(key, {}).get("verdict") == "UNACCEPTABLE"; jh = bool(j.get("hard_fail"))
            tp += h and jh; fp += jh and not h; fn += h and not jh; tn += (not h and not jh)
            if jh and not h: fps.append((key, j.get("hard_fail_reason", ""), j.get("unsupported_claims", [])))
    print(f"{tag}: TP={tp} FP={fp} FN={fn} TN={tn} recall={tp/max(1,tp+fn):.0%} precision={tp/max(1,tp+fp):.0%} agreement={(tp+tn)/(tp+fp+fn+tn):.0%}")
    if "-v" in tags[-1:] or True:
        for k, why, uc in fps[:40]: print("  FP", k, why[:70], uc[:2])
