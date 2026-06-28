done = function(summary, latency, requests)
  io.write("\n--- Latency Percentiles ---\n")
  local percentiles = {50, 75, 90, 99, 99.9}
  for _, p in ipairs(percentiles) do
    local val = latency:percentile(p)
    io.write(string.format("  p%-5g  %6.2fms\n", p, val / 1000))
  end
  io.write(string.format("  max    %6.2fms\n", latency.max / 1000))
end