# Apply Vivado run properties for one ML/DSE trial.
#
# Usage:
#   vivado -mode batch -source ml_synth/tcl/apply_strategy.tcl \
#     -tclargs <project.xpr> synth_1.strategy="Vivado Synthesis Defaults" \
#     impl_1.steps.route_design.args.directive=Explore

if {![info exists ::argv] || [llength $::argv] < 1} {
  puts "ERROR: Missing project path."
  puts {USAGE: apply_strategy.tcl <project.xpr> [<run>.<property>=<value> ...]}
  exit 1
}

set project_xpr [file normalize [lindex $::argv 0]]
if {![file exists $project_xpr]} {
  puts "ERROR: Project file not found: $project_xpr"
  exit 1
}

open_project $project_xpr

set applied 0
foreach assignment [lrange $::argv 1 end] {
  set eq_idx [string first "=" $assignment]
  if {$eq_idx < 1} {
    puts "ERROR: Bad assignment '$assignment'. Expected <run>.<property>=<value>."
    exit 1
  }

  set lhs [string range $assignment 0 [expr {$eq_idx - 1}]]
  set value [string range $assignment [expr {$eq_idx + 1}] end]
  set dot_idx [string first "." $lhs]
  if {$dot_idx < 1} {
    puts "ERROR: Bad assignment '$assignment'. Left side must start with a run name."
    exit 1
  }

  set run_name [string range $lhs 0 [expr {$dot_idx - 1}]]
  set property_name [string range $lhs [expr {$dot_idx + 1}] end]
  set run_obj [get_runs -quiet $run_name]
  if {[llength $run_obj] == 0} {
    puts "WARNING: Run '$run_name' not found; skipping '$property_name'."
    continue
  }

  puts "INFO: set_property -name $property_name -value {$value} -objects $run_name"
  if {[catch {set_property -name $property_name -value $value -objects $run_obj} err]} {
    puts "ERROR: Failed to set $run_name.$property_name=$value: $err"
    exit 1
  }
  incr applied
}

if {$applied == 0} {
  puts "WARNING: No run properties were applied."
} else {
  save_project
  puts "INFO: Applied $applied Vivado run properties."
}

close_project
exit 0
