(module
  (import "env" "pow" (func $pow (param f64 f64) (result f64)))
  (memory (export "memory") 1 1024)
  (global $heap (mut i32) (i32.const 0))

  (func (export "reset_allocator")
    (global.set $heap (i32.const 0)))

  (func (export "allocate") (param $size i32) (result i32)
    (local $start i32) (local $end i32) (local $current i32) (local $pages i32)
    (local.set $start (global.get $heap))
    (local.set $end
      (i32.and
        (i32.add (i32.add (local.get $start) (local.get $size)) (i32.const 7))
        (i32.const -8)))
    (local.set $current (i32.mul (memory.size) (i32.const 65536)))
    (if (i32.gt_u (local.get $end) (local.get $current))
      (then
        (local.set $pages
          (i32.div_u
            (i32.add (i32.sub (local.get $end) (local.get $current)) (i32.const 65535))
            (i32.const 65536)))
        (drop (memory.grow (local.get $pages)))))
    (global.set $heap (local.get $end))
    (local.get $start))

  (func (export "advance_state")
    (param $count i32)
    (param $h i32) (param $hu i32) (param $hv i32)
    (param $rh i32) (param $rhu i32) (param $rhv i32)
    (param $area i32) (param $manning i32)
    (param $dt f64) (param $gravity f64) (param $minimum_depth f64)
    (result i32)
    (local $i i32) (local $offset i32) (local $invalid i32)
    (local $cell_area f64) (local $depth f64) (local $mx f64) (local $my f64)
    (local $roughness f64) (local $speed f64) (local $damping f64)
    (block $done
      (loop $next
        (br_if $done (i32.ge_u (local.get $i) (local.get $count)))
        (local.set $offset (i32.shl (local.get $i) (i32.const 3)))
        (local.set $cell_area (f64.load (i32.add (local.get $area) (local.get $offset))))
        (local.set $depth
          (f64.sub
            (f64.load (i32.add (local.get $h) (local.get $offset)))
            (f64.div
              (f64.mul (local.get $dt) (f64.load (i32.add (local.get $rh) (local.get $offset))))
              (local.get $cell_area))))
        (if (f64.lt (local.get $depth) (local.get $minimum_depth))
          (then
            (local.set $invalid (i32.add (local.get $invalid) (i32.const 1)))
            (local.set $depth (local.get $minimum_depth))))
        (local.set $mx
          (f64.sub
            (f64.load (i32.add (local.get $hu) (local.get $offset)))
            (f64.div
              (f64.mul (local.get $dt) (f64.load (i32.add (local.get $rhu) (local.get $offset))))
              (local.get $cell_area))))
        (local.set $my
          (f64.sub
            (f64.load (i32.add (local.get $hv) (local.get $offset)))
            (f64.div
              (f64.mul (local.get $dt) (f64.load (i32.add (local.get $rhv) (local.get $offset))))
              (local.get $cell_area))))
        (local.set $roughness (f64.load (i32.add (local.get $manning) (local.get $offset))))
        (local.set $speed
          (f64.div
            (f64.sqrt (f64.add (f64.mul (local.get $mx) (local.get $mx)) (f64.mul (local.get $my) (local.get $my))))
            (local.get $depth)))
        (local.set $damping
          (f64.add
            (f64.const 1)
            (f64.div
              (f64.mul
                (f64.mul
                  (f64.mul (f64.mul (local.get $dt) (local.get $gravity)) (local.get $roughness))
                  (local.get $roughness))
                (local.get $speed))
              (call $pow (local.get $depth) (f64.const 1.3333333333333333)))))
        (f64.store (i32.add (local.get $h) (local.get $offset)) (local.get $depth))
        (f64.store (i32.add (local.get $hu) (local.get $offset)) (f64.div (local.get $mx) (local.get $damping)))
        (f64.store (i32.add (local.get $hv) (local.get $offset)) (f64.div (local.get $my) (local.get $damping)))
        (local.set $i (i32.add (local.get $i) (i32.const 1)))
        (br $next)))
    (local.get $invalid)))
