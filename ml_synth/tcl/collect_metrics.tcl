# Collect post-run Vivado reports for one ML/DSE trial.
#
# Usage:
#   vivado -mode batch -source ml_synth/tcl/collect_metrics.tcl \
#     -tclargs <project.xpr> <out_dir> [impl_1|synth_1]

if {![info exists ::argv] || [llength $::argv] < 2} {
  puts "ERROR: Missing arguments."
  puts {USAGE: collect_metrics.tcl <project.xpr> <out_dir> [run_name]}
  exit 1
}

set project_xpr [file normalize [lindex $::argv 0]]
set out_dir [file normalize [lindex $::argv 1]]
set run_name "impl_1"
if {[llength $::argv] >= 3} {
  set run_name [lindex $::argv 2]
}

if {![file exists $project_xpr]} {
  puts "ERROR: Project file not found: $project_xpr"
  exit 1
}

file mkdir $out_dir
open_project $project_xpr

set run_obj [get_runs -quiet $run_name]
if {[llength $run_obj] == 0} {
  puts "ERROR: Run not found: $run_name"
  exit 1
}

set status_file [file join $out_dir run_status.txt]
set fh [open $status_file "w"]
puts $fh "vivado_version=[version -short]"
puts $fh "project=$project_xpr"
puts $fh "run=$run_name"
puts $fh "status=[get_property STATUS $run_obj]"
puts $fh "strategy=[get_property STRATEGY $run_obj]"
foreach prop {
  steps.synth_design.args.directive
  steps.place_design.args.directive
  steps.phys_opt_design.args.directive
  steps.route_design.args.directive
} {
  if {![catch {set value [get_property $prop $run_obj]}]} {
    puts $fh "$prop=$value"
  }
}
close $fh

if {[catch {open_run $run_name} err]} {
  puts "ERROR: open_run $run_name failed: $err"
  exit 1
}

proc safe_report {label command out_file} {
  puts "INFO: Writing $label report to $out_file"
  if {[catch {uplevel 1 $command} err]} {
    set fh [open $out_file "w"]
    puts $fh "ERROR: $label failed: $err"
    close $fh
    puts "WARNING: $label failed: $err"
  }
}

safe_report "timing_summary" \
  [list report_timing_summary -delay_type max -max_paths 10 -file [file join $out_dir timing_summary.rpt]] \
  [file join $out_dir timing_summary.rpt]
safe_report "utilization" \
  [list report_utilization -file [file join $out_dir utilization.rpt]] \
  [file join $out_dir utilization.rpt]
safe_report "route_status" \
  [list report_route_status -file [file join $out_dir route_status.rpt]] \
  [file join $out_dir route_status.rpt]
safe_report "qor_assessment" \
  [list report_qor_assessment -file [file join $out_dir qor_assessment.rpt]] \
  [file join $out_dir qor_assessment.rpt]

close_project
exit 0
