; Symbolic Traffic SMT encoding (parallel to reachability smt_encoding.smt2)
; Direct serialization of YU Algorithm 1 tau_l expressions.
; SpecLens: comment (= Config_*_weight <pin>) to unpin SR candidate weights.

(declare-fun d_x () Bool)

(assert (<= (+ (ite d_x 0 1)) 1))

; link a_d a -> d cap=95.0 yuAllUp=0.0
(declare-fun load_a_d_a_d
             ()
             Real)
(assert (= load_a_d_a_d (let ((tf0 (ite (not d_x) 1.0 0.0))) (let ((tf1 20.0)) (let ((tf2 (* tf0 tf1))) tf2)))))
(assert (< load_a_d_a_d 95.0))

; link a_d d -> a cap=95.0 yuAllUp=0.0
(declare-fun load_a_d_d_a
             ()
             Real)
(assert (= load_a_d_d_a 0.0))
(assert (< load_a_d_d_a 95.0))

; link a_s a -> s cap=95.0 yuAllUp=0.0
(declare-fun load_a_s_a_s
             ()
             Real)
(assert (= load_a_s_a_s 0.0))
(assert (< load_a_s_a_s 95.0))

; link a_s s -> a cap=95.0 yuAllUp=0.0
(declare-fun load_a_s_s_a
             ()
             Real)
(assert (= load_a_s_s_a 0.0))
(assert (< load_a_s_s_a 95.0))

; link a_x a -> x cap=95.0 yuAllUp=0.0
(declare-fun load_a_x_a_x
             ()
             Real)
(assert (= load_a_x_a_x 0.0))
(assert (< load_a_x_a_x 95.0))

; link a_x x -> a cap=95.0 yuAllUp=0.0
(declare-fun load_a_x_x_a
             ()
             Real)
(assert (= load_a_x_x_a (let ((tf0 (ite (not d_x) 1.0 0.0))) (let ((tf1 20.0)) (let ((tf2 (* tf0 tf1))) tf2)))))
(assert (< load_a_x_x_a 95.0))

; link b_d b -> d cap=95.0 yuAllUp=0.0
(declare-fun load_b_d_b_d
             ()
             Real)
(assert (= load_b_d_b_d 0.0))
(assert (< load_b_d_b_d 95.0))

; link b_d d -> b cap=95.0 yuAllUp=0.0
(declare-fun load_b_d_d_b
             ()
             Real)
(assert (= load_b_d_d_b 0.0))
(assert (< load_b_d_d_b 95.0))

; link b_s b -> s cap=95.0 yuAllUp=0.0
(declare-fun load_b_s_b_s
             ()
             Real)
(assert (= load_b_s_b_s 0.0))
(assert (< load_b_s_b_s 95.0))

; link b_s s -> b cap=95.0 yuAllUp=0.0
(declare-fun load_b_s_s_b
             ()
             Real)
(assert (= load_b_s_s_b 0.0))
(assert (< load_b_s_s_b 95.0))

; link b_x b -> x cap=95.0 yuAllUp=0.0
(declare-fun load_b_x_b_x
             ()
             Real)
(assert (= load_b_x_b_x 0.0))
(assert (< load_b_x_b_x 95.0))

; link b_x x -> b cap=95.0 yuAllUp=0.0
(declare-fun load_b_x_x_b
             ()
             Real)
(assert (= load_b_x_x_b 0.0))
(assert (< load_b_x_x_b 95.0))

; link d_x d -> x cap=95.0 yuAllUp=0.0
(declare-fun load_d_x_d_x
             ()
             Real)
(assert (= load_d_x_d_x 0.0))
(assert (< load_d_x_d_x 95.0))

; link d_x x -> d cap=95.0 yuAllUp=20.0
(declare-fun load_d_x_x_d
             ()
             Real)
(assert (= load_d_x_x_d (let ((tf0 (ite d_x 1.0 0.0))) (let ((tf1 20.0)) (let ((tf2 (* tf0 tf1))) tf2)))))
(assert (< load_d_x_x_d 95.0))

(check-sat)
;(get-model)
