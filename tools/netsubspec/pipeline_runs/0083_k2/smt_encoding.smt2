(declare-fun Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip
             ()
             (_ BitVec 32))
(declare-fun Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask
             ()
             (_ BitVec 32))
(declare-fun Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__length () Int)
(declare-fun Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start
             ()
             Int)
(declare-fun Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end
             ()
             Int)
(declare-fun Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable
             ()
             Bool)
(declare-fun Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action
             ()
             Bool)
(declare-fun Config_d_RoutingPolicy_BGP_ORIGINATE__Seq10__Line1__match_prefixlist_enable
             ()
             Bool)
(declare-fun Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip
             ()
             (_ BitVec 32))
(declare-fun Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask
             ()
             (_ BitVec 32))
(declare-fun Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__length () Int)
(declare-fun Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start
             ()
             Int)
(declare-fun Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end
             ()
             Int)
(declare-fun Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable
             ()
             Bool)
(declare-fun Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action
             ()
             Bool)
(declare-fun Config_x_RoutingPolicy_X_IN_FROM_A__Seq10__Line1__match_prefixlist_enable
             ()
             Bool)
(declare-fun Config_x_RoutingPolicy_X_IN_FROM_A__Seq10__Line2__set_localpreference_100
             ()
             Int)
(declare-fun Config_x_RoutingPolicy_X_IN_FROM_A__Seq10__Line2__set_localpreference_100enable
             ()
             Bool)
(declare-fun Config_x_RoutingPolicy_X_IN_FROM_B__Seq10__Line1__match_prefixlist_enable
             ()
             Bool)
(declare-fun Config_x_RoutingPolicy_X_IN_FROM_B__Seq10__Line2__set_localpreference_50
             ()
             Int)
(declare-fun Config_x_RoutingPolicy_X_IN_FROM_B__Seq10__Line2__set_localpreference_50enable
             ()
             Bool)
(declare-fun Config_x_RoutingPolicy_X_IN_FROM_D__Seq10__Line1__match_prefixlist_enable
             ()
             Bool)
(declare-fun Config_x_RoutingPolicy_X_IN_FROM_D__Seq10__Line2__set_localpreference_200
             ()
             Int)
(declare-fun Config_x_RoutingPolicy_X_IN_FROM_D__Seq10__Line2__set_localpreference_200enable
             ()
             Bool)
(declare-fun |0_FAILED-EDGE_b_x| () Int)
(declare-fun |0_FAILED-EDGE_a_d| () Int)
(declare-fun |0_FAILED-EDGE_b_s| () Int)
(declare-fun |0_FAILED-EDGE_b_d| () Int)
(declare-fun |0_FAILED-EDGE_d_x| () Int)
(declare-fun |0_FAILED-EDGE_a_x| () Int)
(declare-fun |0_FAILED-EDGE_a_s| () Int)
(declare-fun |0_FAILED-EDGE_d_Loopback0| () Int)
(declare-fun |0_FAILED-NODE_a| () Int)
(declare-fun |0_FAILED-NODE_d| () Int)
(declare-fun |0_FAILED-NODE_s| () Int)
(declare-fun |0_FAILED-NODE_b| () Int)
(declare-fun |0_FAILED-NODE_x| () Int)
(declare-fun |0_dst-port| () Int)
(declare-fun |0_src-port| () Int)
(declare-fun |0_icmp-type| () Int)
(declare-fun |0_ip-protocol| () Int)
(declare-fun |0_icmp-code| () Int)
(declare-fun |0_a_OVERALL_BEST_None_routerID| () Int)
(declare-fun |0_a_OVERALL_BEST_None_med| () Int)
(declare-fun |0_a_OVERALL_BEST_None_localPref| () Int)
(declare-fun |0_a_OVERALL_BEST_None_metric| () Int)
(declare-fun |0_a_OVERALL_BEST_None_prefixLength| () Int)
(declare-fun |0_b_OVERALL_BEST_None_routerID| () Int)
(declare-fun |0_b_OVERALL_BEST_None_med| () Int)
(declare-fun |0_b_OVERALL_BEST_None_localPref| () Int)
(declare-fun |0_b_OVERALL_BEST_None_metric| () Int)
(declare-fun |0_b_OVERALL_BEST_None_prefixLength| () Int)
(declare-fun |0_s_OVERALL_BEST_None_med| () Int)
(declare-fun |0_s_OVERALL_BEST_None_localPref| () Int)
(declare-fun |0_s_OVERALL_BEST_None_metric| () Int)
(declare-fun |0_s_OVERALL_BEST_None_prefixLength| () Int)
(declare-fun |0_d_OVERALL_BEST_None_routerID| () Int)
(declare-fun |0_d_OVERALL_BEST_None_adminDist| () Int)
(declare-fun |0_d_OVERALL_BEST_None_med| () Int)
(declare-fun |0_d_OVERALL_BEST_None_localPref| () Int)
(declare-fun |0_d_OVERALL_BEST_None_metric| () Int)
(declare-fun |0_d_OVERALL_BEST_None_prefixLength| () Int)
(declare-fun |0_d_BGP_BEST_None_routerID| () Int)
(declare-fun |0_d_BGP_BEST_None_med| () Int)
(declare-fun |0_d_BGP_BEST_None_localPref| () Int)
(declare-fun |0_d_BGP_BEST_None_metric| () Int)
(declare-fun |0_d_BGP_BEST_None_prefixLength| () Int)
(declare-fun |0_d_CONNECTED_BEST_None_prefixLength| () Int)
(declare-fun |0_x_OVERALL_BEST_None_routerID| () Int)
(declare-fun |0_x_OVERALL_BEST_None_med| () Int)
(declare-fun |0_x_OVERALL_BEST_None_localPref| () Int)
(declare-fun |0_x_OVERALL_BEST_None_metric| () Int)
(declare-fun |0_x_OVERALL_BEST_None_prefixLength| () Int)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/0_med| () Int)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/0_localPref| () Int)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/0_metric| () Int)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/0_prefixLength| () Int)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/0_med| () Int)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref| () Int)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/0_metric| () Int)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength| () Int)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/1_med| () Int)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/1_localPref| () Int)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/1_metric| () Int)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/1_prefixLength| () Int)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/1_med| () Int)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref| () Int)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/1_metric| () Int)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength| () Int)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/2_med| () Int)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/2_localPref| () Int)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/2_metric| () Int)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/2_prefixLength| () Int)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/2_med| () Int)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref| () Int)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/2_metric| () Int)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength| () Int)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/1_med| () Int)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/1_localPref| () Int)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/1_metric| () Int)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/1_prefixLength| () Int)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/1_med| () Int)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref| () Int)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/1_metric| () Int)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/1_med| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/1_localPref| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/1_metric| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/1_prefixLength| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/1_med| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/1_metric| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/0_med| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/0_localPref| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/0_metric| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/0_prefixLength| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/0_med| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/0_metric| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/2_med| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/2_localPref| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/2_metric| () Int)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/2_prefixLength| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/2_med| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/2_metric| () Int)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength| () Int)
(declare-fun |0_d_CONNECTED_IMPORT_Loopback0_prefixLength| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/2_med| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/2_localPref| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/2_metric| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/2_prefixLength| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/2_med| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/2_metric| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/1_med| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/1_localPref| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/1_metric| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/1_prefixLength| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/1_med| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/1_metric| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/0_med| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/0_localPref| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/0_metric| () Int)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/0_prefixLength| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/0_med| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/0_metric| () Int)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength| () Int)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted| () Bool)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_x_GigabitEthernet0/1| () Bool)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted| () Bool)
(declare-fun |0_a_OVERALL_BEST_None_permitted| () Bool)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted| () Bool)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_d_GigabitEthernet0/1| () Bool)
(declare-fun |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted| () Bool)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted| () Bool)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_x_GigabitEthernet0/2| () Bool)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted| () Bool)
(declare-fun |0_b_OVERALL_BEST_None_permitted| () Bool)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted| () Bool)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_d_GigabitEthernet0/2| () Bool)
(declare-fun |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted| () Bool)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_a_GigabitEthernet0/1| () Bool)
(declare-fun |0_d_OVERALL_BEST_None_history| () (_ BitVec 1))
(declare-fun |0_d_OVERALL_BEST_None_permitted| () Bool)
(declare-fun |0_dst-ip| () (_ BitVec 32))
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted| () Bool)
(declare-fun |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_x_GigabitEthernet0/0| () Bool)
(declare-fun |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted| () Bool)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_b_GigabitEthernet0/1| () Bool)
(declare-fun |0_d_CONNECTED_IMPORT_Loopback0_permitted| () Bool)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_b_GigabitEthernet0/2| () Bool)
(declare-fun |0_x_OVERALL_BEST_None_permitted| () Bool)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_a_GigabitEthernet0/0| () Bool)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_d_GigabitEthernet0/0| () Bool)
(declare-fun |0_d_BGP_BEST_None_permitted| () Bool)
(declare-fun |0_d_CONNECTED_BEST_None_permitted| () Bool)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/0_choice| () Bool)
(declare-fun |0_a_BGP_IMPORT_GigabitEthernet0/1_choice| () Bool)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/1_choice| () Bool)
(declare-fun |0_b_BGP_IMPORT_GigabitEthernet0/2_choice| () Bool)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/1_choice| () Bool)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/2_choice| () Bool)
(declare-fun |0_d_BGP_IMPORT_GigabitEthernet0/0_choice| () Bool)
(declare-fun |0_d_CONNECTED_IMPORT_Loopback0_choice| () Bool)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/0_choice| () Bool)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/2_choice| () Bool)
(declare-fun |0_x_BGP_IMPORT_GigabitEthernet0/1_choice| () Bool)
(declare-fun |0_s_OVERALL_BEST_None_permitted| () Bool)
(declare-fun |0_CONTROL-FORWARDING_a_GigabitEthernet0/2| () Bool)
(declare-fun |0_CONTROL-FORWARDING_b_GigabitEthernet0/0| () Bool)
(declare-fun |0_CONTROL-FORWARDING_s_GigabitEthernet0/1| () Bool)
(declare-fun |0_CONTROL-FORWARDING_s_GigabitEthernet0/0| () Bool)
(declare-fun |0_CONTROL-FORWARDING_d_Loopback0| () Bool)
(declare-fun |0_DATA-FORWARDING_a_GigabitEthernet0/0| () Bool)
(declare-fun |0_DATA-FORWARDING_a_GigabitEthernet0/2| () Bool)
(declare-fun |0_DATA-FORWARDING_a_GigabitEthernet0/1| () Bool)
(declare-fun |0_DATA-FORWARDING_b_GigabitEthernet0/2| () Bool)
(declare-fun |0_DATA-FORWARDING_b_GigabitEthernet0/1| () Bool)
(declare-fun |0_DATA-FORWARDING_b_GigabitEthernet0/0| () Bool)
(declare-fun |0_DATA-FORWARDING_s_GigabitEthernet0/1| () Bool)
(declare-fun |0_DATA-FORWARDING_s_GigabitEthernet0/0| () Bool)
(declare-fun |0_DATA-FORWARDING_d_GigabitEthernet0/1| () Bool)
(declare-fun |0_DATA-FORWARDING_d_GigabitEthernet0/0| () Bool)
(declare-fun |0_DATA-FORWARDING_d_Loopback0| () Bool)
(declare-fun |0_DATA-FORWARDING_d_GigabitEthernet0/2| () Bool)
(declare-fun |0_DATA-FORWARDING_x_GigabitEthernet0/2| () Bool)
(declare-fun |0_DATA-FORWARDING_x_GigabitEthernet0/1| () Bool)
(declare-fun |0_DATA-FORWARDING_x_GigabitEthernet0/0| () Bool)
(declare-fun |0__reachable-id_a| () Int)
(declare-fun |0__reachable_a| () Bool)
(declare-fun |0__reachable-id_b| () Int)
(declare-fun |0__reachable_b| () Bool)
(declare-fun |0__reachable-id_s| () Int)
(declare-fun |0__reachable_s| () Bool)
(declare-fun |0__reachable-id_d| () Int)
(declare-fun |0__reachable_d| () Bool)
(declare-fun |0__reachable-id_x| () Int)
(declare-fun |0__reachable_x| () Bool)
(assert (= Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip #x05050505))
(assert (= Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask #xffffffff))
(assert (= Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__length 32))
(assert (= Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start 32))
(assert (= Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end 32))
(assert (= Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable true))
(assert (= Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action true))
(assert (>= Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start
    Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__length))
(assert (>= Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end
    Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__length))
(assert (= Config_d_RoutingPolicy_BGP_ORIGINATE__Seq10__Line1__match_prefixlist_enable
   true))
(assert (= Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip #x05050505))
(assert (= Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask #xffffffff))
(assert (= Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__length 32))
(assert (= Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start 32))
(assert (= Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end 32))
(assert (= Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable true))
(assert (= Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action true))
(assert (>= Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start
    Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__length))
(assert (>= Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end
    Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__length))
(assert (= Config_x_RoutingPolicy_X_IN_FROM_A__Seq10__Line1__match_prefixlist_enable
   true))
(assert (= Config_x_RoutingPolicy_X_IN_FROM_A__Seq10__Line2__set_localpreference_100
   100))
(assert (= Config_x_RoutingPolicy_X_IN_FROM_A__Seq10__Line2__set_localpreference_100enable
   true))
(assert (= Config_x_RoutingPolicy_X_IN_FROM_B__Seq10__Line1__match_prefixlist_enable
   true))
(assert (= Config_x_RoutingPolicy_X_IN_FROM_B__Seq10__Line2__set_localpreference_50 50))
(assert (= Config_x_RoutingPolicy_X_IN_FROM_B__Seq10__Line2__set_localpreference_50enable
   true))
(assert (= Config_x_RoutingPolicy_X_IN_FROM_D__Seq10__Line1__match_prefixlist_enable
   true))
(assert (= Config_x_RoutingPolicy_X_IN_FROM_D__Seq10__Line2__set_localpreference_200
   200))
(assert (= Config_x_RoutingPolicy_X_IN_FROM_D__Seq10__Line2__set_localpreference_200enable
   true))
(assert (>= |0_FAILED-EDGE_b_x| 0))
(assert (<= |0_FAILED-EDGE_b_x| 1))
(assert (>= |0_FAILED-EDGE_a_d| 0))
(assert (<= |0_FAILED-EDGE_a_d| 1))
(assert (>= |0_FAILED-EDGE_b_s| 0))
(assert (<= |0_FAILED-EDGE_b_s| 1))
(assert (>= |0_FAILED-EDGE_b_d| 0))
(assert (<= |0_FAILED-EDGE_b_d| 1))
(assert (>= |0_FAILED-EDGE_d_x| 0))
(assert (<= |0_FAILED-EDGE_d_x| 1))
(assert (>= |0_FAILED-EDGE_a_x| 0))
(assert (<= |0_FAILED-EDGE_a_x| 1))
(assert (>= |0_FAILED-EDGE_a_s| 0))
(assert (<= |0_FAILED-EDGE_a_s| 1))
(assert (>= |0_FAILED-EDGE_d_Loopback0| 0))
(assert (<= |0_FAILED-EDGE_d_Loopback0| 1))
(assert (<= (+ 0
       |0_FAILED-EDGE_b_x|
       |0_FAILED-EDGE_a_d|
       |0_FAILED-EDGE_b_s|
       |0_FAILED-EDGE_b_d|
       |0_FAILED-EDGE_d_x|
       |0_FAILED-EDGE_a_x|
       |0_FAILED-EDGE_a_s|
       |0_FAILED-EDGE_d_Loopback0|)
    2))
(assert (>= |0_FAILED-NODE_a| 0))
(assert (<= |0_FAILED-NODE_a| 1))
(assert (>= |0_FAILED-NODE_d| 0))
(assert (<= |0_FAILED-NODE_d| 1))
(assert (>= |0_FAILED-NODE_s| 0))
(assert (<= |0_FAILED-NODE_s| 1))
(assert (>= |0_FAILED-NODE_b| 0))
(assert (<= |0_FAILED-NODE_b| 1))
(assert (>= |0_FAILED-NODE_x| 0))
(assert (<= |0_FAILED-NODE_x| 1))
(assert (= |0_FAILED-NODE_a| 0))
(assert (= |0_FAILED-NODE_d| 0))
(assert (= |0_FAILED-NODE_s| 0))
(assert (= |0_FAILED-NODE_b| 0))
(assert (= |0_FAILED-NODE_x| 0))
(assert (>= |0_dst-port| 0))
(assert (>= |0_src-port| 0))
(assert (< |0_dst-port| 65536))
(assert (< |0_src-port| 65536))
(assert (>= |0_icmp-type| 0))
(assert (>= |0_ip-protocol| 0))
(assert (< |0_icmp-type| 256))
(assert (<= |0_ip-protocol| 256))
(assert (>= |0_icmp-code| 0))
(assert (< |0_icmp-code| 16))
(assert (>= |0_a_OVERALL_BEST_None_routerID| 0))
(assert (>= |0_a_OVERALL_BEST_None_med| 0))
(assert (< |0_a_OVERALL_BEST_None_med| 4294967296))
(assert (>= |0_a_OVERALL_BEST_None_localPref| 0))
(assert (< |0_a_OVERALL_BEST_None_localPref| 4294967296))
(assert (>= |0_a_OVERALL_BEST_None_metric| 0))
(assert (< |0_a_OVERALL_BEST_None_metric| 65536))
(assert (>= |0_a_OVERALL_BEST_None_prefixLength| 0))
(assert (<= |0_a_OVERALL_BEST_None_prefixLength| 32))
(assert (>= |0_b_OVERALL_BEST_None_routerID| 0))
(assert (>= |0_b_OVERALL_BEST_None_med| 0))
(assert (< |0_b_OVERALL_BEST_None_med| 4294967296))
(assert (>= |0_b_OVERALL_BEST_None_localPref| 0))
(assert (< |0_b_OVERALL_BEST_None_localPref| 4294967296))
(assert (>= |0_b_OVERALL_BEST_None_metric| 0))
(assert (< |0_b_OVERALL_BEST_None_metric| 65536))
(assert (>= |0_b_OVERALL_BEST_None_prefixLength| 0))
(assert (<= |0_b_OVERALL_BEST_None_prefixLength| 32))
(assert (>= |0_s_OVERALL_BEST_None_med| 0))
(assert (< |0_s_OVERALL_BEST_None_med| 4294967296))
(assert (>= |0_s_OVERALL_BEST_None_localPref| 0))
(assert (< |0_s_OVERALL_BEST_None_localPref| 4294967296))
(assert (>= |0_s_OVERALL_BEST_None_metric| 0))
(assert (< |0_s_OVERALL_BEST_None_metric| 65536))
(assert (>= |0_s_OVERALL_BEST_None_prefixLength| 0))
(assert (<= |0_s_OVERALL_BEST_None_prefixLength| 32))
(assert (>= |0_d_OVERALL_BEST_None_routerID| 0))
(assert (>= |0_d_OVERALL_BEST_None_adminDist| 0))
(assert (< |0_d_OVERALL_BEST_None_adminDist| 256))
(assert (>= |0_d_OVERALL_BEST_None_med| 0))
(assert (< |0_d_OVERALL_BEST_None_med| 4294967296))
(assert (>= |0_d_OVERALL_BEST_None_localPref| 0))
(assert (< |0_d_OVERALL_BEST_None_localPref| 4294967296))
(assert (>= |0_d_OVERALL_BEST_None_metric| 0))
(assert (< |0_d_OVERALL_BEST_None_metric| 65536))
(assert (>= |0_d_OVERALL_BEST_None_prefixLength| 0))
(assert (<= |0_d_OVERALL_BEST_None_prefixLength| 32))
(assert (>= |0_d_BGP_BEST_None_routerID| 0))
(assert (>= |0_d_BGP_BEST_None_med| 0))
(assert (< |0_d_BGP_BEST_None_med| 4294967296))
(assert (>= |0_d_BGP_BEST_None_localPref| 0))
(assert (< |0_d_BGP_BEST_None_localPref| 4294967296))
(assert (>= |0_d_BGP_BEST_None_metric| 0))
(assert (< |0_d_BGP_BEST_None_metric| 65536))
(assert (>= |0_d_BGP_BEST_None_prefixLength| 0))
(assert (<= |0_d_BGP_BEST_None_prefixLength| 32))
(assert (>= |0_d_CONNECTED_BEST_None_prefixLength| 0))
(assert (<= |0_d_CONNECTED_BEST_None_prefixLength| 32))
(assert (>= |0_x_OVERALL_BEST_None_routerID| 0))
(assert (>= |0_x_OVERALL_BEST_None_med| 0))
(assert (< |0_x_OVERALL_BEST_None_med| 4294967296))
(assert (>= |0_x_OVERALL_BEST_None_localPref| 0))
(assert (< |0_x_OVERALL_BEST_None_localPref| 4294967296))
(assert (>= |0_x_OVERALL_BEST_None_metric| 0))
(assert (< |0_x_OVERALL_BEST_None_metric| 65536))
(assert (>= |0_x_OVERALL_BEST_None_prefixLength| 0))
(assert (<= |0_x_OVERALL_BEST_None_prefixLength| 32))
(assert (>= |0_a_BGP_EXPORT_GigabitEthernet0/0_med| 0))
(assert (< |0_a_BGP_EXPORT_GigabitEthernet0/0_med| 4294967296))
(assert (>= |0_a_BGP_EXPORT_GigabitEthernet0/0_localPref| 0))
(assert (< |0_a_BGP_EXPORT_GigabitEthernet0/0_localPref| 4294967296))
(assert (>= |0_a_BGP_EXPORT_GigabitEthernet0/0_metric| 0))
(assert (< |0_a_BGP_EXPORT_GigabitEthernet0/0_metric| 65536))
(assert (>= |0_a_BGP_EXPORT_GigabitEthernet0/0_prefixLength| 0))
(assert (<= |0_a_BGP_EXPORT_GigabitEthernet0/0_prefixLength| 32))
(assert (>= |0_a_BGP_IMPORT_GigabitEthernet0/0_med| 0))
(assert (< |0_a_BGP_IMPORT_GigabitEthernet0/0_med| 4294967296))
(assert (>= |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref| 0))
(assert (< |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref| 4294967296))
(assert (>= |0_a_BGP_IMPORT_GigabitEthernet0/0_metric| 0))
(assert (< |0_a_BGP_IMPORT_GigabitEthernet0/0_metric| 65536))
(assert (>= |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength| 0))
(assert (<= |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength| 32))
(assert (>= |0_a_BGP_EXPORT_GigabitEthernet0/1_med| 0))
(assert (< |0_a_BGP_EXPORT_GigabitEthernet0/1_med| 4294967296))
(assert (>= |0_a_BGP_EXPORT_GigabitEthernet0/1_localPref| 0))
(assert (< |0_a_BGP_EXPORT_GigabitEthernet0/1_localPref| 4294967296))
(assert (>= |0_a_BGP_EXPORT_GigabitEthernet0/1_metric| 0))
(assert (< |0_a_BGP_EXPORT_GigabitEthernet0/1_metric| 65536))
(assert (>= |0_a_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 0))
(assert (<= |0_a_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 32))
(assert (>= |0_a_BGP_IMPORT_GigabitEthernet0/1_med| 0))
(assert (< |0_a_BGP_IMPORT_GigabitEthernet0/1_med| 4294967296))
(assert (>= |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref| 0))
(assert (< |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref| 4294967296))
(assert (>= |0_a_BGP_IMPORT_GigabitEthernet0/1_metric| 0))
(assert (< |0_a_BGP_IMPORT_GigabitEthernet0/1_metric| 65536))
(assert (>= |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 0))
(assert (<= |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 32))
(assert (>= |0_b_BGP_EXPORT_GigabitEthernet0/2_med| 0))
(assert (< |0_b_BGP_EXPORT_GigabitEthernet0/2_med| 4294967296))
(assert (>= |0_b_BGP_EXPORT_GigabitEthernet0/2_localPref| 0))
(assert (< |0_b_BGP_EXPORT_GigabitEthernet0/2_localPref| 4294967296))
(assert (>= |0_b_BGP_EXPORT_GigabitEthernet0/2_metric| 0))
(assert (< |0_b_BGP_EXPORT_GigabitEthernet0/2_metric| 65536))
(assert (>= |0_b_BGP_EXPORT_GigabitEthernet0/2_prefixLength| 0))
(assert (<= |0_b_BGP_EXPORT_GigabitEthernet0/2_prefixLength| 32))
(assert (>= |0_b_BGP_IMPORT_GigabitEthernet0/2_med| 0))
(assert (< |0_b_BGP_IMPORT_GigabitEthernet0/2_med| 4294967296))
(assert (>= |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref| 0))
(assert (< |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref| 4294967296))
(assert (>= |0_b_BGP_IMPORT_GigabitEthernet0/2_metric| 0))
(assert (< |0_b_BGP_IMPORT_GigabitEthernet0/2_metric| 65536))
(assert (>= |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength| 0))
(assert (<= |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength| 32))
(assert (>= |0_b_BGP_EXPORT_GigabitEthernet0/1_med| 0))
(assert (< |0_b_BGP_EXPORT_GigabitEthernet0/1_med| 4294967296))
(assert (>= |0_b_BGP_EXPORT_GigabitEthernet0/1_localPref| 0))
(assert (< |0_b_BGP_EXPORT_GigabitEthernet0/1_localPref| 4294967296))
(assert (>= |0_b_BGP_EXPORT_GigabitEthernet0/1_metric| 0))
(assert (< |0_b_BGP_EXPORT_GigabitEthernet0/1_metric| 65536))
(assert (>= |0_b_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 0))
(assert (<= |0_b_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 32))
(assert (>= |0_b_BGP_IMPORT_GigabitEthernet0/1_med| 0))
(assert (< |0_b_BGP_IMPORT_GigabitEthernet0/1_med| 4294967296))
(assert (>= |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref| 0))
(assert (< |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref| 4294967296))
(assert (>= |0_b_BGP_IMPORT_GigabitEthernet0/1_metric| 0))
(assert (< |0_b_BGP_IMPORT_GigabitEthernet0/1_metric| 65536))
(assert (>= |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 0))
(assert (<= |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 32))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/1_med| 0))
(assert (< |0_d_BGP_EXPORT_GigabitEthernet0/1_med| 4294967296))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/1_localPref| 0))
(assert (< |0_d_BGP_EXPORT_GigabitEthernet0/1_localPref| 4294967296))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/1_metric| 0))
(assert (< |0_d_BGP_EXPORT_GigabitEthernet0/1_metric| 65536))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 0))
(assert (<= |0_d_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 32))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/1_med| 0))
(assert (< |0_d_BGP_IMPORT_GigabitEthernet0/1_med| 4294967296))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref| 0))
(assert (< |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref| 4294967296))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/1_metric| 0))
(assert (< |0_d_BGP_IMPORT_GigabitEthernet0/1_metric| 65536))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 0))
(assert (<= |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 32))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/0_med| 0))
(assert (< |0_d_BGP_EXPORT_GigabitEthernet0/0_med| 4294967296))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/0_localPref| 0))
(assert (< |0_d_BGP_EXPORT_GigabitEthernet0/0_localPref| 4294967296))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/0_metric| 0))
(assert (< |0_d_BGP_EXPORT_GigabitEthernet0/0_metric| 65536))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/0_prefixLength| 0))
(assert (<= |0_d_BGP_EXPORT_GigabitEthernet0/0_prefixLength| 32))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/0_med| 0))
(assert (< |0_d_BGP_IMPORT_GigabitEthernet0/0_med| 4294967296))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref| 0))
(assert (< |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref| 4294967296))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/0_metric| 0))
(assert (< |0_d_BGP_IMPORT_GigabitEthernet0/0_metric| 65536))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength| 0))
(assert (<= |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength| 32))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/2_med| 0))
(assert (< |0_d_BGP_EXPORT_GigabitEthernet0/2_med| 4294967296))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/2_localPref| 0))
(assert (< |0_d_BGP_EXPORT_GigabitEthernet0/2_localPref| 4294967296))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/2_metric| 0))
(assert (< |0_d_BGP_EXPORT_GigabitEthernet0/2_metric| 65536))
(assert (>= |0_d_BGP_EXPORT_GigabitEthernet0/2_prefixLength| 0))
(assert (<= |0_d_BGP_EXPORT_GigabitEthernet0/2_prefixLength| 32))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/2_med| 0))
(assert (< |0_d_BGP_IMPORT_GigabitEthernet0/2_med| 4294967296))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref| 0))
(assert (< |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref| 4294967296))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/2_metric| 0))
(assert (< |0_d_BGP_IMPORT_GigabitEthernet0/2_metric| 65536))
(assert (>= |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength| 0))
(assert (<= |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength| 32))
(assert (>= |0_d_CONNECTED_IMPORT_Loopback0_prefixLength| 0))
(assert (<= |0_d_CONNECTED_IMPORT_Loopback0_prefixLength| 32))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/2_med| 0))
(assert (< |0_x_BGP_EXPORT_GigabitEthernet0/2_med| 4294967296))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/2_localPref| 0))
(assert (< |0_x_BGP_EXPORT_GigabitEthernet0/2_localPref| 4294967296))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/2_metric| 0))
(assert (< |0_x_BGP_EXPORT_GigabitEthernet0/2_metric| 65536))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/2_prefixLength| 0))
(assert (<= |0_x_BGP_EXPORT_GigabitEthernet0/2_prefixLength| 32))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/2_med| 0))
(assert (< |0_x_BGP_IMPORT_GigabitEthernet0/2_med| 4294967296))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref| 0))
(assert (< |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref| 4294967296))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/2_metric| 0))
(assert (< |0_x_BGP_IMPORT_GigabitEthernet0/2_metric| 65536))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength| 0))
(assert (<= |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength| 32))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/1_med| 0))
(assert (< |0_x_BGP_EXPORT_GigabitEthernet0/1_med| 4294967296))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/1_localPref| 0))
(assert (< |0_x_BGP_EXPORT_GigabitEthernet0/1_localPref| 4294967296))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/1_metric| 0))
(assert (< |0_x_BGP_EXPORT_GigabitEthernet0/1_metric| 65536))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 0))
(assert (<= |0_x_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 32))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/1_med| 0))
(assert (< |0_x_BGP_IMPORT_GigabitEthernet0/1_med| 4294967296))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref| 0))
(assert (< |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref| 4294967296))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/1_metric| 0))
(assert (< |0_x_BGP_IMPORT_GigabitEthernet0/1_metric| 65536))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 0))
(assert (<= |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 32))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/0_med| 0))
(assert (< |0_x_BGP_EXPORT_GigabitEthernet0/0_med| 4294967296))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/0_localPref| 0))
(assert (< |0_x_BGP_EXPORT_GigabitEthernet0/0_localPref| 4294967296))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/0_metric| 0))
(assert (< |0_x_BGP_EXPORT_GigabitEthernet0/0_metric| 65536))
(assert (>= |0_x_BGP_EXPORT_GigabitEthernet0/0_prefixLength| 0))
(assert (<= |0_x_BGP_EXPORT_GigabitEthernet0/0_prefixLength| 32))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/0_med| 0))
(assert (< |0_x_BGP_IMPORT_GigabitEthernet0/0_med| 4294967296))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref| 0))
(assert (< |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref| 4294967296))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/0_metric| 0))
(assert (< |0_x_BGP_IMPORT_GigabitEthernet0/0_metric| 65536))
(assert (>= |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength| 0))
(assert (<= |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength| 32))
(assert (let ((a!1 (ite true
                (ite true
                     (and (= |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|
                             |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|)
                          (= |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength|
                             |0_x_BGP_EXPORT_GigabitEthernet0/1_prefixLength|)
                          true
                          (= |0_a_BGP_IMPORT_GigabitEthernet0/0_med|
                             |0_x_BGP_EXPORT_GigabitEthernet0/1_med|)
                          (= |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref|
                             |0_x_BGP_EXPORT_GigabitEthernet0/1_localPref|)
                          (= |0_a_BGP_IMPORT_GigabitEthernet0/0_metric|
                             |0_x_BGP_EXPORT_GigabitEthernet0/1_metric|)
                          true
                          true
                          true
                          true
                          true
                          true
                          true
                          true)
                     (not |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|))
                (not |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_x_GigabitEthernet0/1|)
            true
            |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|
            (= |0_FAILED-EDGE_a_x| 0)
            (= |0_FAILED-NODE_a| 0))
       a!1
       (not |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|))))
(assert (let ((a!1 (and (= |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|
                   |0_a_OVERALL_BEST_None_permitted|)
                (= |0_a_BGP_EXPORT_GigabitEthernet0/0_prefixLength|
                   |0_a_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_a_BGP_EXPORT_GigabitEthernet0/0_med| 0)
                (= |0_a_BGP_EXPORT_GigabitEthernet0/0_localPref| 100)
                (= |0_a_BGP_EXPORT_GigabitEthernet0/0_metric|
                   (ite true (+ |0_a_OVERALL_BEST_None_metric| 1) 1))
                true
                true
                true
                true
                true
                true
                true
                true)))
  (ite (and true
            true
            |0_a_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_a_x| 0)
            (= |0_FAILED-NODE_x| 0))
       (ite true
            (ite true a!1 (not |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|))
            (not |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|))
       (not |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|))))
(assert (let ((a!1 (ite true
                (ite true
                     (and (= |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|
                             |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|)
                          (= |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength|
                             |0_d_BGP_EXPORT_GigabitEthernet0/1_prefixLength|)
                          true
                          (= |0_a_BGP_IMPORT_GigabitEthernet0/1_med|
                             |0_d_BGP_EXPORT_GigabitEthernet0/1_med|)
                          (= |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref|
                             |0_d_BGP_EXPORT_GigabitEthernet0/1_localPref|)
                          (= |0_a_BGP_IMPORT_GigabitEthernet0/1_metric|
                             |0_d_BGP_EXPORT_GigabitEthernet0/1_metric|)
                          true
                          true
                          true
                          true
                          true
                          true
                          true
                          true)
                     (not |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|))
                (not |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_d_GigabitEthernet0/1|)
            true
            |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|
            (= |0_FAILED-EDGE_a_d| 0)
            (= |0_FAILED-NODE_a| 0))
       a!1
       (not |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|))))
(assert (let ((a!1 (and (= |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|
                   |0_a_OVERALL_BEST_None_permitted|)
                (= |0_a_BGP_EXPORT_GigabitEthernet0/1_prefixLength|
                   |0_a_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_a_BGP_EXPORT_GigabitEthernet0/1_med| 0)
                (= |0_a_BGP_EXPORT_GigabitEthernet0/1_localPref| 100)
                (= |0_a_BGP_EXPORT_GigabitEthernet0/1_metric|
                   (ite true (+ |0_a_OVERALL_BEST_None_metric| 1) 1))
                true
                true
                true
                true
                true
                true
                true
                true)))
  (ite (and true
            true
            |0_a_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_a_d| 0)
            (= |0_FAILED-NODE_d| 0))
       (ite true
            (ite true a!1 (not |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|))
            (not |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|))
       (not |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|))))
(assert (let ((a!1 (ite true
                (ite true
                     (and (= |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|
                             |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|)
                          (= |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength|
                             |0_x_BGP_EXPORT_GigabitEthernet0/2_prefixLength|)
                          true
                          (= |0_b_BGP_IMPORT_GigabitEthernet0/2_med|
                             |0_x_BGP_EXPORT_GigabitEthernet0/2_med|)
                          (= |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref|
                             |0_x_BGP_EXPORT_GigabitEthernet0/2_localPref|)
                          (= |0_b_BGP_IMPORT_GigabitEthernet0/2_metric|
                             |0_x_BGP_EXPORT_GigabitEthernet0/2_metric|)
                          true
                          true
                          true
                          true
                          true
                          true
                          true
                          true)
                     (not |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|))
                (not |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_x_GigabitEthernet0/2|)
            true
            |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|
            (= |0_FAILED-EDGE_b_x| 0)
            (= |0_FAILED-NODE_b| 0))
       a!1
       (not |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|))))
(assert (let ((a!1 (and (= |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|
                   |0_b_OVERALL_BEST_None_permitted|)
                (= |0_b_BGP_EXPORT_GigabitEthernet0/2_prefixLength|
                   |0_b_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_b_BGP_EXPORT_GigabitEthernet0/2_med| 0)
                (= |0_b_BGP_EXPORT_GigabitEthernet0/2_localPref| 100)
                (= |0_b_BGP_EXPORT_GigabitEthernet0/2_metric|
                   (ite true (+ |0_b_OVERALL_BEST_None_metric| 1) 1))
                true
                true
                true
                true
                true
                true
                true
                true)))
  (ite (and true
            true
            |0_b_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_b_x| 0)
            (= |0_FAILED-NODE_x| 0))
       (ite true
            (ite true a!1 (not |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|))
            (not |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|))
       (not |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|))))
(assert (let ((a!1 (ite true
                (ite true
                     (and (= |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|
                             |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|)
                          (= |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength|
                             |0_d_BGP_EXPORT_GigabitEthernet0/2_prefixLength|)
                          true
                          (= |0_b_BGP_IMPORT_GigabitEthernet0/1_med|
                             |0_d_BGP_EXPORT_GigabitEthernet0/2_med|)
                          (= |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref|
                             |0_d_BGP_EXPORT_GigabitEthernet0/2_localPref|)
                          (= |0_b_BGP_IMPORT_GigabitEthernet0/1_metric|
                             |0_d_BGP_EXPORT_GigabitEthernet0/2_metric|)
                          true
                          true
                          true
                          true
                          true
                          true
                          true
                          true)
                     (not |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|))
                (not |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_d_GigabitEthernet0/2|)
            true
            |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|
            (= |0_FAILED-EDGE_b_d| 0)
            (= |0_FAILED-NODE_b| 0))
       a!1
       (not |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|))))
(assert (let ((a!1 (and (= |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|
                   |0_b_OVERALL_BEST_None_permitted|)
                (= |0_b_BGP_EXPORT_GigabitEthernet0/1_prefixLength|
                   |0_b_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_b_BGP_EXPORT_GigabitEthernet0/1_med| 0)
                (= |0_b_BGP_EXPORT_GigabitEthernet0/1_localPref| 100)
                (= |0_b_BGP_EXPORT_GigabitEthernet0/1_metric|
                   (ite true (+ |0_b_OVERALL_BEST_None_metric| 1) 1))
                true
                true
                true
                true
                true
                true
                true
                true)))
  (ite (and true
            true
            |0_b_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_b_d| 0)
            (= |0_FAILED-NODE_d| 0))
       (ite true
            (ite true a!1 (not |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|))
            (not |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|))
       (not |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|))))
(assert (let ((a!1 (ite true
                (ite true
                     (and (= |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|
                             |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|)
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength|
                             |0_a_BGP_EXPORT_GigabitEthernet0/1_prefixLength|)
                          true
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/1_med|
                             |0_a_BGP_EXPORT_GigabitEthernet0/1_med|)
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref|
                             |0_a_BGP_EXPORT_GigabitEthernet0/1_localPref|)
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/1_metric|
                             |0_a_BGP_EXPORT_GigabitEthernet0/1_metric|)
                          true
                          true
                          true
                          true
                          true
                          true
                          true
                          true)
                     (not |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|))
                (not |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_a_GigabitEthernet0/1|)
            true
            |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|
            (= |0_FAILED-EDGE_a_d| 0)
            (= |0_FAILED-NODE_d| 0))
       a!1
       (not |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|))))
(assert (let ((a!1 (= (bvnot (bvor (bvnot |0_dst-ip|)
                           (bvnot Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask)))
              (bvnot (bvor (bvnot Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip)
                           (bvnot Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask)))))
      (a!3 (and (= |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|
                   |0_d_OVERALL_BEST_None_permitted|)
                (= |0_d_BGP_EXPORT_GigabitEthernet0/1_prefixLength|
                   |0_d_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_d_BGP_EXPORT_GigabitEthernet0/1_med| 0)
                (= |0_d_BGP_EXPORT_GigabitEthernet0/1_localPref| 100)
                (= |0_d_BGP_EXPORT_GigabitEthernet0/1_metric|
                   (ite (= |0_d_OVERALL_BEST_None_history| #b0)
                        (+ |0_d_OVERALL_BEST_None_metric| 1)
                        1))
                true
                true
                true
                true
                true
                true
                true
                true)))
(let ((a!2 (and (= |0_d_OVERALL_BEST_None_history| #b1)
                (or (not Config_d_RoutingPolicy_BGP_ORIGINATE__Seq10__Line1__match_prefixlist_enable)
                    (and Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable
                         (= |0_d_OVERALL_BEST_None_prefixLength|
                            Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start)
                         (= |0_d_OVERALL_BEST_None_prefixLength|
                            Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end)
                         a!1
                         Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action))
                Config_d_RoutingPolicy_BGP_ORIGINATE__Seq10__Line1__match_prefixlist_enable)))
  (ite (and true
            true
            |0_d_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_a_d| 0)
            (= |0_FAILED-NODE_a| 0))
       (ite (or (= |0_d_OVERALL_BEST_None_history| #b0) a!2)
            (ite true a!3 (not |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|))
            (not |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|))
       (not |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|)))))
(assert (let ((a!1 (ite true
                (ite true
                     (and (= |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|
                             |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|)
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength|
                             |0_x_BGP_EXPORT_GigabitEthernet0/0_prefixLength|)
                          true
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/0_med|
                             |0_x_BGP_EXPORT_GigabitEthernet0/0_med|)
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref|
                             |0_x_BGP_EXPORT_GigabitEthernet0/0_localPref|)
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/0_metric|
                             |0_x_BGP_EXPORT_GigabitEthernet0/0_metric|)
                          true
                          true
                          true
                          true
                          true
                          true
                          true
                          true)
                     (not |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|))
                (not |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_x_GigabitEthernet0/0|)
            true
            |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|
            (= |0_FAILED-EDGE_d_x| 0)
            (= |0_FAILED-NODE_d| 0))
       a!1
       (not |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|))))
(assert (let ((a!1 (= (bvnot (bvor (bvnot |0_dst-ip|)
                           (bvnot Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask)))
              (bvnot (bvor (bvnot Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip)
                           (bvnot Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask)))))
      (a!3 (and (= |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|
                   |0_d_OVERALL_BEST_None_permitted|)
                (= |0_d_BGP_EXPORT_GigabitEthernet0/0_prefixLength|
                   |0_d_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_d_BGP_EXPORT_GigabitEthernet0/0_med| 0)
                (= |0_d_BGP_EXPORT_GigabitEthernet0/0_localPref| 100)
                (= |0_d_BGP_EXPORT_GigabitEthernet0/0_metric|
                   (ite (= |0_d_OVERALL_BEST_None_history| #b0)
                        (+ |0_d_OVERALL_BEST_None_metric| 1)
                        1))
                true
                true
                true
                true
                true
                true
                true
                true)))
(let ((a!2 (and (= |0_d_OVERALL_BEST_None_history| #b1)
                (or (not Config_d_RoutingPolicy_BGP_ORIGINATE__Seq10__Line1__match_prefixlist_enable)
                    (and Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable
                         (= |0_d_OVERALL_BEST_None_prefixLength|
                            Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start)
                         (= |0_d_OVERALL_BEST_None_prefixLength|
                            Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end)
                         a!1
                         Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action))
                Config_d_RoutingPolicy_BGP_ORIGINATE__Seq10__Line1__match_prefixlist_enable)))
  (ite (and true
            true
            |0_d_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_d_x| 0)
            (= |0_FAILED-NODE_x| 0))
       (ite (or (= |0_d_OVERALL_BEST_None_history| #b0) a!2)
            (ite true a!3 (not |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|))
            (not |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|))
       (not |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|)))))
(assert (let ((a!1 (ite true
                (ite true
                     (and (= |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|
                             |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|)
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength|
                             |0_b_BGP_EXPORT_GigabitEthernet0/1_prefixLength|)
                          true
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/2_med|
                             |0_b_BGP_EXPORT_GigabitEthernet0/1_med|)
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref|
                             |0_b_BGP_EXPORT_GigabitEthernet0/1_localPref|)
                          (= |0_d_BGP_IMPORT_GigabitEthernet0/2_metric|
                             |0_b_BGP_EXPORT_GigabitEthernet0/1_metric|)
                          true
                          true
                          true
                          true
                          true
                          true
                          true
                          true)
                     (not |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|))
                (not |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_b_GigabitEthernet0/1|)
            true
            |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|
            (= |0_FAILED-EDGE_b_d| 0)
            (= |0_FAILED-NODE_d| 0))
       a!1
       (not |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|))))
(assert (let ((a!1 (= (bvnot (bvor (bvnot |0_dst-ip|)
                           (bvnot Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask)))
              (bvnot (bvor (bvnot Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip)
                           (bvnot Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask)))))
      (a!3 (and (= |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|
                   |0_d_OVERALL_BEST_None_permitted|)
                (= |0_d_BGP_EXPORT_GigabitEthernet0/2_prefixLength|
                   |0_d_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_d_BGP_EXPORT_GigabitEthernet0/2_med| 0)
                (= |0_d_BGP_EXPORT_GigabitEthernet0/2_localPref| 100)
                (= |0_d_BGP_EXPORT_GigabitEthernet0/2_metric|
                   (ite (= |0_d_OVERALL_BEST_None_history| #b0)
                        (+ |0_d_OVERALL_BEST_None_metric| 1)
                        1))
                true
                true
                true
                true
                true
                true
                true
                true)))
(let ((a!2 (and (= |0_d_OVERALL_BEST_None_history| #b1)
                (or (not Config_d_RoutingPolicy_BGP_ORIGINATE__Seq10__Line1__match_prefixlist_enable)
                    (and Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable
                         (= |0_d_OVERALL_BEST_None_prefixLength|
                            Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start)
                         (= |0_d_OVERALL_BEST_None_prefixLength|
                            Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end)
                         a!1
                         Config_d_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action))
                Config_d_RoutingPolicy_BGP_ORIGINATE__Seq10__Line1__match_prefixlist_enable)))
  (ite (and true
            true
            |0_d_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_b_d| 0)
            (= |0_FAILED-NODE_b| 0))
       (ite (or (= |0_d_OVERALL_BEST_None_history| #b0) a!2)
            (ite true a!3 (not |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|))
            (not |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|))
       (not |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|)))))
(assert (ite (and true
          (= (bvand |0_dst-ip| #xffffffff) (bvand #x05050505 #xffffffff))
          (= |0_FAILED-EDGE_d_Loopback0| 0)
          (= |0_FAILED-NODE_d| 0))
     (and |0_d_CONNECTED_IMPORT_Loopback0_permitted|
          (= |0_d_CONNECTED_IMPORT_Loopback0_prefixLength| 32)
          true
          true
          true)
     (not |0_d_CONNECTED_IMPORT_Loopback0_permitted|)))
(assert (let ((a!1 (= (bvnot (bvor (bvnot |0_dst-ip|)
                           (bvnot Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask)))
              (bvnot (bvor (bvnot Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip)
                           (bvnot Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask))))))
(let ((a!2 (and (or (not Config_x_RoutingPolicy_X_IN_FROM_B__Seq10__Line1__match_prefixlist_enable)
                    (and Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable
                         (= |0_b_BGP_EXPORT_GigabitEthernet0/2_prefixLength|
                            Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start)
                         (= |0_b_BGP_EXPORT_GigabitEthernet0/2_prefixLength|
                            Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end)
                         a!1
                         Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action))
                Config_x_RoutingPolicy_X_IN_FROM_B__Seq10__Line1__match_prefixlist_enable)))
(let ((a!3 (ite true
                (and (= |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|
                        |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|)
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength|
                        |0_b_BGP_EXPORT_GigabitEthernet0/2_prefixLength|)
                     true
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/2_med|
                        |0_b_BGP_EXPORT_GigabitEthernet0/2_med|)
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref|
                        (ite a!2
                             Config_x_RoutingPolicy_X_IN_FROM_B__Seq10__Line2__set_localpreference_50
                             |0_b_BGP_EXPORT_GigabitEthernet0/2_localPref|))
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/2_metric|
                        |0_b_BGP_EXPORT_GigabitEthernet0/2_metric|)
                     true
                     true
                     true
                     true
                     true
                     true
                     true
                     true)
                (not |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_b_GigabitEthernet0/2|)
            true
            |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|
            (= |0_FAILED-EDGE_b_x| 0)
            (= |0_FAILED-NODE_x| 0))
       (ite a!2 a!3 (not |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|))
       (not |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|))))))
(assert (let ((a!1 (and (= |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|
                   |0_x_OVERALL_BEST_None_permitted|)
                (= |0_x_BGP_EXPORT_GigabitEthernet0/2_prefixLength|
                   |0_x_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_x_BGP_EXPORT_GigabitEthernet0/2_med| 0)
                (= |0_x_BGP_EXPORT_GigabitEthernet0/2_localPref| 100)
                (= |0_x_BGP_EXPORT_GigabitEthernet0/2_metric|
                   (ite true (+ |0_x_OVERALL_BEST_None_metric| 1) 1))
                true
                true
                true
                true
                true
                true
                true
                true)))
  (ite (and true
            true
            |0_x_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_b_x| 0)
            (= |0_FAILED-NODE_b| 0))
       (ite true
            (ite true a!1 (not |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|))
            (not |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|))
       (not |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|))))
(assert (let ((a!1 (= (bvnot (bvor (bvnot |0_dst-ip|)
                           (bvnot Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask)))
              (bvnot (bvor (bvnot Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip)
                           (bvnot Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask))))))
(let ((a!2 (and (or (not Config_x_RoutingPolicy_X_IN_FROM_A__Seq10__Line1__match_prefixlist_enable)
                    (and Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable
                         (= |0_a_BGP_EXPORT_GigabitEthernet0/0_prefixLength|
                            Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start)
                         (= |0_a_BGP_EXPORT_GigabitEthernet0/0_prefixLength|
                            Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end)
                         a!1
                         Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action))
                Config_x_RoutingPolicy_X_IN_FROM_A__Seq10__Line1__match_prefixlist_enable)))
(let ((a!3 (ite true
                (and (= |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|
                        |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|)
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength|
                        |0_a_BGP_EXPORT_GigabitEthernet0/0_prefixLength|)
                     true
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/1_med|
                        |0_a_BGP_EXPORT_GigabitEthernet0/0_med|)
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref|
                        (ite a!2
                             Config_x_RoutingPolicy_X_IN_FROM_A__Seq10__Line2__set_localpreference_100
                             |0_a_BGP_EXPORT_GigabitEthernet0/0_localPref|))
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/1_metric|
                        |0_a_BGP_EXPORT_GigabitEthernet0/0_metric|)
                     true
                     true
                     true
                     true
                     true
                     true
                     true
                     true)
                (not |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_a_GigabitEthernet0/0|)
            true
            |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|
            (= |0_FAILED-EDGE_a_x| 0)
            (= |0_FAILED-NODE_x| 0))
       (ite a!2 a!3 (not |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|))
       (not |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|))))))
(assert (let ((a!1 (and (= |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|
                   |0_x_OVERALL_BEST_None_permitted|)
                (= |0_x_BGP_EXPORT_GigabitEthernet0/1_prefixLength|
                   |0_x_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_x_BGP_EXPORT_GigabitEthernet0/1_med| 0)
                (= |0_x_BGP_EXPORT_GigabitEthernet0/1_localPref| 100)
                (= |0_x_BGP_EXPORT_GigabitEthernet0/1_metric|
                   (ite true (+ |0_x_OVERALL_BEST_None_metric| 1) 1))
                true
                true
                true
                true
                true
                true
                true
                true)))
  (ite (and true
            true
            |0_x_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_a_x| 0)
            (= |0_FAILED-NODE_a| 0))
       (ite true
            (ite true a!1 (not |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|))
            (not |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|))
       (not |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|))))
(assert (let ((a!1 (= (bvnot (bvor (bvnot |0_dst-ip|)
                           (bvnot Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask)))
              (bvnot (bvor (bvnot Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__ip)
                           (bvnot Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__mask))))))
(let ((a!2 (and (or (not Config_x_RoutingPolicy_X_IN_FROM_D__Seq10__Line1__match_prefixlist_enable)
                    (and Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__enable
                         (= |0_d_BGP_EXPORT_GigabitEthernet0/0_prefixLength|
                            Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_start)
                         (= |0_d_BGP_EXPORT_GigabitEthernet0/0_prefixLength|
                            Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__prefix_range_end)
                         a!1
                         Config_x_RouteFilterList_D_LOOPBACK__Line1__5_5_5_5__action))
                Config_x_RoutingPolicy_X_IN_FROM_D__Seq10__Line1__match_prefixlist_enable)))
(let ((a!3 (ite true
                (and (= |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|
                        |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|)
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength|
                        |0_d_BGP_EXPORT_GigabitEthernet0/0_prefixLength|)
                     true
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/0_med|
                        |0_d_BGP_EXPORT_GigabitEthernet0/0_med|)
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref|
                        (ite a!2
                             Config_x_RoutingPolicy_X_IN_FROM_D__Seq10__Line2__set_localpreference_200
                             |0_d_BGP_EXPORT_GigabitEthernet0/0_localPref|))
                     (= |0_x_BGP_IMPORT_GigabitEthernet0/0_metric|
                        |0_d_BGP_EXPORT_GigabitEthernet0/0_metric|)
                     true
                     true
                     true
                     true
                     true
                     true
                     true
                     true)
                (not |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|))))
  (ite (and (not |0_CONTROL-FORWARDING_d_GigabitEthernet0/0|)
            true
            |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|
            (= |0_FAILED-EDGE_d_x| 0)
            (= |0_FAILED-NODE_x| 0))
       (ite a!2 a!3 (not |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|))
       (not |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|))))))
(assert (let ((a!1 (and (= |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|
                   |0_x_OVERALL_BEST_None_permitted|)
                (= |0_x_BGP_EXPORT_GigabitEthernet0/0_prefixLength|
                   |0_x_OVERALL_BEST_None_prefixLength|)
                true
                (= |0_x_BGP_EXPORT_GigabitEthernet0/0_med| 0)
                (= |0_x_BGP_EXPORT_GigabitEthernet0/0_localPref| 100)
                (= |0_x_BGP_EXPORT_GigabitEthernet0/0_metric|
                   (ite true (+ |0_x_OVERALL_BEST_None_metric| 1) 1))
                true
                true
                true
                true
                true
                true
                true
                true)))
  (ite (and true
            true
            |0_x_OVERALL_BEST_None_permitted|
            (= |0_FAILED-EDGE_d_x| 0)
            (= |0_FAILED-NODE_d| 0))
       (ite true
            (ite true a!1 (not |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|))
            (not |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|))
       (not |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|))))
(assert (=> |0_a_OVERALL_BEST_None_permitted| true))
(assert (=> |0_b_OVERALL_BEST_None_permitted| true))
(assert (=> |0_x_OVERALL_BEST_None_permitted| true))
(assert (let ((a!1 (and true
                (or false
                    (and true (<= |0_a_OVERALL_BEST_None_routerID| 16843009))))))
(let ((a!2 (and (= |0_a_OVERALL_BEST_None_med|
                   |0_a_BGP_IMPORT_GigabitEthernet0/0_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_a_OVERALL_BEST_None_metric|
                  |0_a_BGP_IMPORT_GigabitEthernet0/0_metric|)
               (and (= |0_a_OVERALL_BEST_None_metric|
                       |0_a_BGP_IMPORT_GigabitEthernet0/0_metric|)
                    (or (< |0_a_OVERALL_BEST_None_med|
                           |0_a_BGP_IMPORT_GigabitEthernet0/0_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_a_OVERALL_BEST_None_localPref|
                       |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref|)
                    (and (= |0_a_OVERALL_BEST_None_localPref|
                            |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref|)
                         a!3)))))
  (=> |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|
      (or (> |0_a_OVERALL_BEST_None_prefixLength|
             |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
          (and (= |0_a_OVERALL_BEST_None_prefixLength|
                  |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
               (or false a!4)))))))))
(assert (let ((a!1 (and true
                (or false
                    (and true (<= |0_a_OVERALL_BEST_None_routerID| 84215045))))))
(let ((a!2 (and (= |0_a_OVERALL_BEST_None_med|
                   |0_a_BGP_IMPORT_GigabitEthernet0/1_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_a_OVERALL_BEST_None_metric|
                  |0_a_BGP_IMPORT_GigabitEthernet0/1_metric|)
               (and (= |0_a_OVERALL_BEST_None_metric|
                       |0_a_BGP_IMPORT_GigabitEthernet0/1_metric|)
                    (or (< |0_a_OVERALL_BEST_None_med|
                           |0_a_BGP_IMPORT_GigabitEthernet0/1_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_a_OVERALL_BEST_None_localPref|
                       |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref|)
                    (and (= |0_a_OVERALL_BEST_None_localPref|
                            |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref|)
                         a!3)))))
  (=> |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|
      (or (> |0_a_OVERALL_BEST_None_prefixLength|
             |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
          (and (= |0_a_OVERALL_BEST_None_prefixLength|
                  |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
               (or false a!4)))))))))
(assert (= (or |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|
       |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|)
   |0_a_OVERALL_BEST_None_permitted|))
(assert (=> (or |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|
        |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (or (and |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|
             (= |0_a_OVERALL_BEST_None_prefixLength|
                |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
             true
             (= |0_a_OVERALL_BEST_None_localPref|
                |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref|)
             (= |0_a_OVERALL_BEST_None_metric|
                |0_a_BGP_IMPORT_GigabitEthernet0/0_metric|)
             (= |0_a_OVERALL_BEST_None_med|
                |0_a_BGP_IMPORT_GigabitEthernet0/0_med|)
             true
             true
             (= |0_a_OVERALL_BEST_None_routerID| 16843009)
             true
             true
             true
             true
             true)
        (and |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|
             (= |0_a_OVERALL_BEST_None_prefixLength|
                |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
             true
             (= |0_a_OVERALL_BEST_None_localPref|
                |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref|)
             (= |0_a_OVERALL_BEST_None_metric|
                |0_a_BGP_IMPORT_GigabitEthernet0/1_metric|)
             (= |0_a_OVERALL_BEST_None_med|
                |0_a_BGP_IMPORT_GigabitEthernet0/1_med|)
             true
             true
             (= |0_a_OVERALL_BEST_None_routerID| 84215045)
             true
             true
             true
             true
             true))))
(assert (let ((a!1 (and true
                (or false
                    (and true (<= |0_b_OVERALL_BEST_None_routerID| 84215045))))))
(let ((a!2 (and (= |0_b_OVERALL_BEST_None_med|
                   |0_b_BGP_IMPORT_GigabitEthernet0/1_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_b_OVERALL_BEST_None_metric|
                  |0_b_BGP_IMPORT_GigabitEthernet0/1_metric|)
               (and (= |0_b_OVERALL_BEST_None_metric|
                       |0_b_BGP_IMPORT_GigabitEthernet0/1_metric|)
                    (or (< |0_b_OVERALL_BEST_None_med|
                           |0_b_BGP_IMPORT_GigabitEthernet0/1_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_b_OVERALL_BEST_None_localPref|
                       |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref|)
                    (and (= |0_b_OVERALL_BEST_None_localPref|
                            |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref|)
                         a!3)))))
  (=> |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|
      (or (> |0_b_OVERALL_BEST_None_prefixLength|
             |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
          (and (= |0_b_OVERALL_BEST_None_prefixLength|
                  |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
               (or false a!4)))))))))
(assert (let ((a!1 (and true
                (or false
                    (and true (<= |0_b_OVERALL_BEST_None_routerID| 16843009))))))
(let ((a!2 (and (= |0_b_OVERALL_BEST_None_med|
                   |0_b_BGP_IMPORT_GigabitEthernet0/2_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_b_OVERALL_BEST_None_metric|
                  |0_b_BGP_IMPORT_GigabitEthernet0/2_metric|)
               (and (= |0_b_OVERALL_BEST_None_metric|
                       |0_b_BGP_IMPORT_GigabitEthernet0/2_metric|)
                    (or (< |0_b_OVERALL_BEST_None_med|
                           |0_b_BGP_IMPORT_GigabitEthernet0/2_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_b_OVERALL_BEST_None_localPref|
                       |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref|)
                    (and (= |0_b_OVERALL_BEST_None_localPref|
                            |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref|)
                         a!3)))))
  (=> |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|
      (or (> |0_b_OVERALL_BEST_None_prefixLength|
             |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
          (and (= |0_b_OVERALL_BEST_None_prefixLength|
                  |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
               (or false a!4)))))))))
(assert (= (or |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|
       |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|)
   |0_b_OVERALL_BEST_None_permitted|))
(assert (=> (or |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|
        |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (or (and |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|
             (= |0_b_OVERALL_BEST_None_prefixLength|
                |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
             true
             (= |0_b_OVERALL_BEST_None_localPref|
                |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref|)
             (= |0_b_OVERALL_BEST_None_metric|
                |0_b_BGP_IMPORT_GigabitEthernet0/1_metric|)
             (= |0_b_OVERALL_BEST_None_med|
                |0_b_BGP_IMPORT_GigabitEthernet0/1_med|)
             true
             true
             (= |0_b_OVERALL_BEST_None_routerID| 84215045)
             true
             true
             true
             true
             true)
        (and |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|
             (= |0_b_OVERALL_BEST_None_prefixLength|
                |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
             true
             (= |0_b_OVERALL_BEST_None_localPref|
                |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref|)
             (= |0_b_OVERALL_BEST_None_metric|
                |0_b_BGP_IMPORT_GigabitEthernet0/2_metric|)
             (= |0_b_OVERALL_BEST_None_med|
                |0_b_BGP_IMPORT_GigabitEthernet0/2_med|)
             true
             true
             (= |0_b_OVERALL_BEST_None_routerID| 16843009)
             true
             true
             true
             true
             true))))
(assert (let ((a!1 (and true
                (or false (and true (<= |0_d_BGP_BEST_None_routerID| 33686018))))))
(let ((a!2 (and (= |0_d_BGP_BEST_None_med|
                   |0_d_BGP_IMPORT_GigabitEthernet0/1_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_d_BGP_BEST_None_metric|
                  |0_d_BGP_IMPORT_GigabitEthernet0/1_metric|)
               (and (= |0_d_BGP_BEST_None_metric|
                       |0_d_BGP_IMPORT_GigabitEthernet0/1_metric|)
                    (or (< |0_d_BGP_BEST_None_med|
                           |0_d_BGP_IMPORT_GigabitEthernet0/1_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_d_BGP_BEST_None_localPref|
                       |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref|)
                    (and (= |0_d_BGP_BEST_None_localPref|
                            |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref|)
                         a!3)))))
  (=> |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|
      (or (> |0_d_BGP_BEST_None_prefixLength|
             |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
          (and (= |0_d_BGP_BEST_None_prefixLength|
                  |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
               (or false a!4)))))))))
(assert (let ((a!1 (and true
                (or false (and true (<= |0_d_BGP_BEST_None_routerID| 67372036))))))
(let ((a!2 (and (= |0_d_BGP_BEST_None_med|
                   |0_d_BGP_IMPORT_GigabitEthernet0/2_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_d_BGP_BEST_None_metric|
                  |0_d_BGP_IMPORT_GigabitEthernet0/2_metric|)
               (and (= |0_d_BGP_BEST_None_metric|
                       |0_d_BGP_IMPORT_GigabitEthernet0/2_metric|)
                    (or (< |0_d_BGP_BEST_None_med|
                           |0_d_BGP_IMPORT_GigabitEthernet0/2_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_d_BGP_BEST_None_localPref|
                       |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref|)
                    (and (= |0_d_BGP_BEST_None_localPref|
                            |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref|)
                         a!3)))))
  (=> |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|
      (or (> |0_d_BGP_BEST_None_prefixLength|
             |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
          (and (= |0_d_BGP_BEST_None_prefixLength|
                  |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
               (or false a!4)))))))))
(assert (let ((a!1 (and true
                (or false (and true (<= |0_d_BGP_BEST_None_routerID| 16843009))))))
(let ((a!2 (and (= |0_d_BGP_BEST_None_med|
                   |0_d_BGP_IMPORT_GigabitEthernet0/0_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_d_BGP_BEST_None_metric|
                  |0_d_BGP_IMPORT_GigabitEthernet0/0_metric|)
               (and (= |0_d_BGP_BEST_None_metric|
                       |0_d_BGP_IMPORT_GigabitEthernet0/0_metric|)
                    (or (< |0_d_BGP_BEST_None_med|
                           |0_d_BGP_IMPORT_GigabitEthernet0/0_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_d_BGP_BEST_None_localPref|
                       |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref|)
                    (and (= |0_d_BGP_BEST_None_localPref|
                            |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref|)
                         a!3)))))
  (=> |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|
      (or (> |0_d_BGP_BEST_None_prefixLength|
             |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
          (and (= |0_d_BGP_BEST_None_prefixLength|
                  |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
               (or false a!4)))))))))
(assert (= (or |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|
       |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|
       |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|)
   |0_d_BGP_BEST_None_permitted|))
(assert (=> (or |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|
        |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|
        |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (or (and |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|
             (= |0_d_BGP_BEST_None_prefixLength|
                |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
             true
             (= |0_d_BGP_BEST_None_localPref|
                |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref|)
             (= |0_d_BGP_BEST_None_metric|
                |0_d_BGP_IMPORT_GigabitEthernet0/1_metric|)
             (= |0_d_BGP_BEST_None_med| |0_d_BGP_IMPORT_GigabitEthernet0/1_med|)
             true
             true
             (= |0_d_BGP_BEST_None_routerID| 33686018)
             true
             true
             true
             true
             true)
        (and |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|
             (= |0_d_BGP_BEST_None_prefixLength|
                |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
             true
             (= |0_d_BGP_BEST_None_localPref|
                |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref|)
             (= |0_d_BGP_BEST_None_metric|
                |0_d_BGP_IMPORT_GigabitEthernet0/2_metric|)
             (= |0_d_BGP_BEST_None_med| |0_d_BGP_IMPORT_GigabitEthernet0/2_med|)
             true
             true
             (= |0_d_BGP_BEST_None_routerID| 67372036)
             true
             true
             true
             true
             true)
        (and |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|
             (= |0_d_BGP_BEST_None_prefixLength|
                |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
             true
             (= |0_d_BGP_BEST_None_localPref|
                |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref|)
             (= |0_d_BGP_BEST_None_metric|
                |0_d_BGP_IMPORT_GigabitEthernet0/0_metric|)
             (= |0_d_BGP_BEST_None_med| |0_d_BGP_IMPORT_GigabitEthernet0/0_med|)
             true
             true
             (= |0_d_BGP_BEST_None_routerID| 16843009)
             true
             true
             true
             true
             true))))
(assert (let ((a!1 (or false (and true (or false (and true true))))))
(let ((a!2 (or false (and true (or false (and true a!1))))))
(let ((a!3 (or false (and true (or false (and true a!2))))))
(let ((a!4 (or (> |0_d_CONNECTED_BEST_None_prefixLength|
                  |0_d_CONNECTED_IMPORT_Loopback0_prefixLength|)
               (and (= |0_d_CONNECTED_BEST_None_prefixLength|
                       |0_d_CONNECTED_IMPORT_Loopback0_prefixLength|)
                    (or false (and true a!3))))))
  (=> |0_d_CONNECTED_IMPORT_Loopback0_permitted| a!4))))))
(assert (= |0_d_CONNECTED_IMPORT_Loopback0_permitted|
   |0_d_CONNECTED_BEST_None_permitted|))
(assert (=> |0_d_CONNECTED_IMPORT_Loopback0_permitted|
    (and |0_d_CONNECTED_IMPORT_Loopback0_permitted|
         (= |0_d_CONNECTED_BEST_None_prefixLength|
            |0_d_CONNECTED_IMPORT_Loopback0_prefixLength|)
         true
         true
         true
         true
         true
         true
         true
         true
         true
         true
         true
         true)))
(assert (let ((a!1 (and true
                (or false
                    (and true (<= |0_x_OVERALL_BEST_None_routerID| 84215045))))))
(let ((a!2 (and (= |0_x_OVERALL_BEST_None_med|
                   |0_x_BGP_IMPORT_GigabitEthernet0/0_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_x_OVERALL_BEST_None_metric|
                  |0_x_BGP_IMPORT_GigabitEthernet0/0_metric|)
               (and (= |0_x_OVERALL_BEST_None_metric|
                       |0_x_BGP_IMPORT_GigabitEthernet0/0_metric|)
                    (or (< |0_x_OVERALL_BEST_None_med|
                           |0_x_BGP_IMPORT_GigabitEthernet0/0_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_x_OVERALL_BEST_None_localPref|
                       |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref|)
                    (and (= |0_x_OVERALL_BEST_None_localPref|
                            |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref|)
                         a!3)))))
  (=> |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|
      (or (> |0_x_OVERALL_BEST_None_prefixLength|
             |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
          (and (= |0_x_OVERALL_BEST_None_prefixLength|
                  |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
               (or false a!4)))))))))
(assert (let ((a!1 (and true
                (or false
                    (and true (<= |0_x_OVERALL_BEST_None_routerID| 67372036))))))
(let ((a!2 (and (= |0_x_OVERALL_BEST_None_med|
                   |0_x_BGP_IMPORT_GigabitEthernet0/2_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_x_OVERALL_BEST_None_metric|
                  |0_x_BGP_IMPORT_GigabitEthernet0/2_metric|)
               (and (= |0_x_OVERALL_BEST_None_metric|
                       |0_x_BGP_IMPORT_GigabitEthernet0/2_metric|)
                    (or (< |0_x_OVERALL_BEST_None_med|
                           |0_x_BGP_IMPORT_GigabitEthernet0/2_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_x_OVERALL_BEST_None_localPref|
                       |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref|)
                    (and (= |0_x_OVERALL_BEST_None_localPref|
                            |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref|)
                         a!3)))))
  (=> |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|
      (or (> |0_x_OVERALL_BEST_None_prefixLength|
             |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
          (and (= |0_x_OVERALL_BEST_None_prefixLength|
                  |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
               (or false a!4)))))))))
(assert (let ((a!1 (and true
                (or false
                    (and true (<= |0_x_OVERALL_BEST_None_routerID| 33686018))))))
(let ((a!2 (and (= |0_x_OVERALL_BEST_None_med|
                   |0_x_BGP_IMPORT_GigabitEthernet0/1_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_x_OVERALL_BEST_None_metric|
                  |0_x_BGP_IMPORT_GigabitEthernet0/1_metric|)
               (and (= |0_x_OVERALL_BEST_None_metric|
                       |0_x_BGP_IMPORT_GigabitEthernet0/1_metric|)
                    (or (< |0_x_OVERALL_BEST_None_med|
                           |0_x_BGP_IMPORT_GigabitEthernet0/1_med|)
                        a!2)))))
(let ((a!4 (and true
                (or (> |0_x_OVERALL_BEST_None_localPref|
                       |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref|)
                    (and (= |0_x_OVERALL_BEST_None_localPref|
                            |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref|)
                         a!3)))))
  (=> |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|
      (or (> |0_x_OVERALL_BEST_None_prefixLength|
             |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
          (and (= |0_x_OVERALL_BEST_None_prefixLength|
                  |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
               (or false a!4)))))))))
(assert (= (or |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|
       |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|
       |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|)
   |0_x_OVERALL_BEST_None_permitted|))
(assert (=> (or |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|
        |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|
        |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (or (and |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|
             (= |0_x_OVERALL_BEST_None_prefixLength|
                |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
             true
             (= |0_x_OVERALL_BEST_None_localPref|
                |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref|)
             (= |0_x_OVERALL_BEST_None_metric|
                |0_x_BGP_IMPORT_GigabitEthernet0/0_metric|)
             (= |0_x_OVERALL_BEST_None_med|
                |0_x_BGP_IMPORT_GigabitEthernet0/0_med|)
             true
             true
             (= |0_x_OVERALL_BEST_None_routerID| 84215045)
             true
             true
             true
             true
             true)
        (and |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|
             (= |0_x_OVERALL_BEST_None_prefixLength|
                |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
             true
             (= |0_x_OVERALL_BEST_None_localPref|
                |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref|)
             (= |0_x_OVERALL_BEST_None_metric|
                |0_x_BGP_IMPORT_GigabitEthernet0/2_metric|)
             (= |0_x_OVERALL_BEST_None_med|
                |0_x_BGP_IMPORT_GigabitEthernet0/2_med|)
             true
             true
             (= |0_x_OVERALL_BEST_None_routerID| 67372036)
             true
             true
             true
             true
             true)
        (and |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|
             (= |0_x_OVERALL_BEST_None_prefixLength|
                |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
             true
             (= |0_x_OVERALL_BEST_None_localPref|
                |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref|)
             (= |0_x_OVERALL_BEST_None_metric|
                |0_x_BGP_IMPORT_GigabitEthernet0/1_metric|)
             (= |0_x_OVERALL_BEST_None_med|
                |0_x_BGP_IMPORT_GigabitEthernet0/1_med|)
             true
             true
             (= |0_x_OVERALL_BEST_None_routerID| 33686018)
             true
             true
             true
             true
             true))))
(assert (= |0_a_BGP_IMPORT_GigabitEthernet0/0_choice|
   (and |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|
        (= |0_a_OVERALL_BEST_None_prefixLength|
           |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
        true
        (= |0_a_OVERALL_BEST_None_localPref|
           |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref|)
        (= |0_a_OVERALL_BEST_None_metric|
           |0_a_BGP_IMPORT_GigabitEthernet0/0_metric|)
        (= |0_a_OVERALL_BEST_None_med| |0_a_BGP_IMPORT_GigabitEthernet0/0_med|)
        true
        true
        (= |0_a_OVERALL_BEST_None_routerID| 16843009)
        true
        true
        true
        true
        true)))
(assert (= |0_a_BGP_IMPORT_GigabitEthernet0/1_choice|
   (and |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|
        (= |0_a_OVERALL_BEST_None_prefixLength|
           |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
        true
        (= |0_a_OVERALL_BEST_None_localPref|
           |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref|)
        (= |0_a_OVERALL_BEST_None_metric|
           |0_a_BGP_IMPORT_GigabitEthernet0/1_metric|)
        (= |0_a_OVERALL_BEST_None_med| |0_a_BGP_IMPORT_GigabitEthernet0/1_med|)
        true
        true
        (= |0_a_OVERALL_BEST_None_routerID| 84215045)
        true
        true
        true
        true
        true)))
(assert (= |0_b_BGP_IMPORT_GigabitEthernet0/1_choice|
   (and |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|
        (= |0_b_OVERALL_BEST_None_prefixLength|
           |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
        true
        (= |0_b_OVERALL_BEST_None_localPref|
           |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref|)
        (= |0_b_OVERALL_BEST_None_metric|
           |0_b_BGP_IMPORT_GigabitEthernet0/1_metric|)
        (= |0_b_OVERALL_BEST_None_med| |0_b_BGP_IMPORT_GigabitEthernet0/1_med|)
        true
        true
        (= |0_b_OVERALL_BEST_None_routerID| 84215045)
        true
        true
        true
        true
        true)))
(assert (= |0_b_BGP_IMPORT_GigabitEthernet0/2_choice|
   (and |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|
        (= |0_b_OVERALL_BEST_None_prefixLength|
           |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
        true
        (= |0_b_OVERALL_BEST_None_localPref|
           |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref|)
        (= |0_b_OVERALL_BEST_None_metric|
           |0_b_BGP_IMPORT_GigabitEthernet0/2_metric|)
        (= |0_b_OVERALL_BEST_None_med| |0_b_BGP_IMPORT_GigabitEthernet0/2_med|)
        true
        true
        (= |0_b_OVERALL_BEST_None_routerID| 16843009)
        true
        true
        true
        true
        true)))
(assert (= |0_d_BGP_IMPORT_GigabitEthernet0/1_choice|
   (and |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|
        (= |0_d_BGP_BEST_None_prefixLength|
           |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
        true
        (= |0_d_BGP_BEST_None_localPref|
           |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref|)
        (= |0_d_BGP_BEST_None_metric|
           |0_d_BGP_IMPORT_GigabitEthernet0/1_metric|)
        (= |0_d_BGP_BEST_None_med| |0_d_BGP_IMPORT_GigabitEthernet0/1_med|)
        true
        true
        (= |0_d_BGP_BEST_None_routerID| 33686018)
        true
        true
        true
        true
        true)))
(assert (= |0_d_BGP_IMPORT_GigabitEthernet0/2_choice|
   (and |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|
        (= |0_d_BGP_BEST_None_prefixLength|
           |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
        true
        (= |0_d_BGP_BEST_None_localPref|
           |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref|)
        (= |0_d_BGP_BEST_None_metric|
           |0_d_BGP_IMPORT_GigabitEthernet0/2_metric|)
        (= |0_d_BGP_BEST_None_med| |0_d_BGP_IMPORT_GigabitEthernet0/2_med|)
        true
        true
        (= |0_d_BGP_BEST_None_routerID| 67372036)
        true
        true
        true
        true
        true)))
(assert (= |0_d_BGP_IMPORT_GigabitEthernet0/0_choice|
   (and |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|
        (= |0_d_BGP_BEST_None_prefixLength|
           |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
        true
        (= |0_d_BGP_BEST_None_localPref|
           |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref|)
        (= |0_d_BGP_BEST_None_metric|
           |0_d_BGP_IMPORT_GigabitEthernet0/0_metric|)
        (= |0_d_BGP_BEST_None_med| |0_d_BGP_IMPORT_GigabitEthernet0/0_med|)
        true
        true
        (= |0_d_BGP_BEST_None_routerID| 16843009)
        true
        true
        true
        true
        true)))
(assert (= |0_d_CONNECTED_IMPORT_Loopback0_choice|
   (and |0_d_CONNECTED_IMPORT_Loopback0_permitted|
        (= |0_d_CONNECTED_BEST_None_prefixLength|
           |0_d_CONNECTED_IMPORT_Loopback0_prefixLength|)
        true
        true
        true
        true
        true
        true
        true
        true
        true
        true
        true
        true)))
(assert (= |0_x_BGP_IMPORT_GigabitEthernet0/0_choice|
   (and |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|
        (= |0_x_OVERALL_BEST_None_prefixLength|
           |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
        true
        (= |0_x_OVERALL_BEST_None_localPref|
           |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref|)
        (= |0_x_OVERALL_BEST_None_metric|
           |0_x_BGP_IMPORT_GigabitEthernet0/0_metric|)
        (= |0_x_OVERALL_BEST_None_med| |0_x_BGP_IMPORT_GigabitEthernet0/0_med|)
        true
        true
        (= |0_x_OVERALL_BEST_None_routerID| 84215045)
        true
        true
        true
        true
        true)))
(assert (= |0_x_BGP_IMPORT_GigabitEthernet0/2_choice|
   (and |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|
        (= |0_x_OVERALL_BEST_None_prefixLength|
           |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
        true
        (= |0_x_OVERALL_BEST_None_localPref|
           |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref|)
        (= |0_x_OVERALL_BEST_None_metric|
           |0_x_BGP_IMPORT_GigabitEthernet0/2_metric|)
        (= |0_x_OVERALL_BEST_None_med| |0_x_BGP_IMPORT_GigabitEthernet0/2_med|)
        true
        true
        (= |0_x_OVERALL_BEST_None_routerID| 67372036)
        true
        true
        true
        true
        true)))
(assert (= |0_x_BGP_IMPORT_GigabitEthernet0/1_choice|
   (and |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|
        (= |0_x_OVERALL_BEST_None_prefixLength|
           |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
        true
        (= |0_x_OVERALL_BEST_None_localPref|
           |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref|)
        (= |0_x_OVERALL_BEST_None_metric|
           |0_x_BGP_IMPORT_GigabitEthernet0/1_metric|)
        (= |0_x_OVERALL_BEST_None_med| |0_x_BGP_IMPORT_GigabitEthernet0/1_med|)
        true
        true
        (= |0_x_OVERALL_BEST_None_routerID| 33686018)
        true
        true
        true
        true
        true)))
(assert (not |0_s_OVERALL_BEST_None_permitted|))
(assert (let ((a!1 (and true
                (or false
                    (and true
                         (<= |0_d_OVERALL_BEST_None_routerID|
                             |0_d_BGP_BEST_None_routerID|))))))
(let ((a!2 (and (= |0_d_OVERALL_BEST_None_med| |0_d_BGP_BEST_None_med|)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_d_OVERALL_BEST_None_metric| |0_d_BGP_BEST_None_metric|)
               (and (= |0_d_OVERALL_BEST_None_metric|
                       |0_d_BGP_BEST_None_metric|)
                    (or (< |0_d_OVERALL_BEST_None_med| |0_d_BGP_BEST_None_med|)
                        a!2)))))
(let ((a!4 (and (= |0_d_OVERALL_BEST_None_adminDist| 20)
                (or (> |0_d_OVERALL_BEST_None_localPref|
                       |0_d_BGP_BEST_None_localPref|)
                    (and (= |0_d_OVERALL_BEST_None_localPref|
                            |0_d_BGP_BEST_None_localPref|)
                         a!3)))))
(let ((a!5 (or (> |0_d_OVERALL_BEST_None_prefixLength|
                  |0_d_BGP_BEST_None_prefixLength|)
               (and (= |0_d_OVERALL_BEST_None_prefixLength|
                       |0_d_BGP_BEST_None_prefixLength|)
                    (or (< |0_d_OVERALL_BEST_None_adminDist| 20) a!4)))))
  (=> |0_d_BGP_BEST_None_permitted| a!5)))))))
(assert (let ((a!1 (and true
                (or false (and true (<= |0_d_OVERALL_BEST_None_routerID| 0))))))
(let ((a!2 (and (= |0_d_OVERALL_BEST_None_med| 0)
                (or false (and true (or false a!1))))))
(let ((a!3 (or (< |0_d_OVERALL_BEST_None_metric| 0)
               (and (= |0_d_OVERALL_BEST_None_metric| 0)
                    (or (< |0_d_OVERALL_BEST_None_med| 0) a!2)))))
(let ((a!4 (and (= |0_d_OVERALL_BEST_None_adminDist| 0)
                (or (> |0_d_OVERALL_BEST_None_localPref| 100)
                    (and (= |0_d_OVERALL_BEST_None_localPref| 100) a!3)))))
(let ((a!5 (or (> |0_d_OVERALL_BEST_None_prefixLength|
                  |0_d_CONNECTED_BEST_None_prefixLength|)
               (and (= |0_d_OVERALL_BEST_None_prefixLength|
                       |0_d_CONNECTED_BEST_None_prefixLength|)
                    (or (< |0_d_OVERALL_BEST_None_adminDist| 0) a!4)))))
  (=> |0_d_CONNECTED_BEST_None_permitted| a!5)))))))
(assert (= (or |0_d_BGP_BEST_None_permitted| |0_d_CONNECTED_BEST_None_permitted|)
   |0_d_OVERALL_BEST_None_permitted|))
(assert (=> (or |0_d_BGP_BEST_None_permitted| |0_d_CONNECTED_BEST_None_permitted|)
    (or (and |0_d_BGP_BEST_None_permitted|
             (= |0_d_OVERALL_BEST_None_prefixLength|
                |0_d_BGP_BEST_None_prefixLength|)
             (= |0_d_OVERALL_BEST_None_adminDist| 20)
             (= |0_d_OVERALL_BEST_None_localPref| |0_d_BGP_BEST_None_localPref|)
             (= |0_d_OVERALL_BEST_None_metric| |0_d_BGP_BEST_None_metric|)
             (= |0_d_OVERALL_BEST_None_med| |0_d_BGP_BEST_None_med|)
             true
             true
             (= |0_d_OVERALL_BEST_None_routerID| |0_d_BGP_BEST_None_routerID|)
             (= |0_d_OVERALL_BEST_None_history| #b0)
             true
             true
             true
             true)
        (and |0_d_CONNECTED_BEST_None_permitted|
             (= |0_d_OVERALL_BEST_None_prefixLength|
                |0_d_CONNECTED_BEST_None_prefixLength|)
             (= |0_d_OVERALL_BEST_None_adminDist| 0)
             (= |0_d_OVERALL_BEST_None_localPref| 100)
             (= |0_d_OVERALL_BEST_None_metric| 0)
             (= |0_d_OVERALL_BEST_None_med| 0)
             true
             true
             true
             (= |0_d_OVERALL_BEST_None_history| #b1)
             true
             true
             true
             true))))
(assert (=> (and true
         |0_a_BGP_IMPORT_GigabitEthernet0/0_choice|
         (= |0_a_OVERALL_BEST_None_prefixLength|
            |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
         true
         (= |0_a_OVERALL_BEST_None_localPref|
            |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref|)
         (= |0_a_OVERALL_BEST_None_metric|
            |0_a_BGP_IMPORT_GigabitEthernet0/0_metric|)
         (= |0_a_OVERALL_BEST_None_med| |0_a_BGP_IMPORT_GigabitEthernet0/0_med|)
         true
         true
         (= |0_a_OVERALL_BEST_None_routerID| 16843009)
         true
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_a_GigabitEthernet0/0|))
(assert (=> (and true
         |0_a_BGP_IMPORT_GigabitEthernet0/1_choice|
         (= |0_a_OVERALL_BEST_None_prefixLength|
            |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
         true
         (= |0_a_OVERALL_BEST_None_localPref|
            |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref|)
         (= |0_a_OVERALL_BEST_None_metric|
            |0_a_BGP_IMPORT_GigabitEthernet0/1_metric|)
         (= |0_a_OVERALL_BEST_None_med| |0_a_BGP_IMPORT_GigabitEthernet0/1_med|)
         true
         true
         (= |0_a_OVERALL_BEST_None_routerID| 84215045)
         true
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_a_GigabitEthernet0/1|))
(assert (= |0_CONTROL-FORWARDING_a_GigabitEthernet0/0|
   (or (and false false)
       (and (not false)
            true
            |0_a_BGP_IMPORT_GigabitEthernet0/0_choice|
            (= |0_a_OVERALL_BEST_None_prefixLength|
               |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
            true
            (= |0_a_OVERALL_BEST_None_localPref|
               |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref|)
            (= |0_a_OVERALL_BEST_None_metric|
               |0_a_BGP_IMPORT_GigabitEthernet0/0_metric|)
            (= |0_a_OVERALL_BEST_None_med|
               |0_a_BGP_IMPORT_GigabitEthernet0/0_med|)
            true
            true
            (= |0_a_OVERALL_BEST_None_routerID| 16843009)
            true
            true
            true
            true
            true))))
(assert (= |0_CONTROL-FORWARDING_a_GigabitEthernet0/2|
   (or (and false false) (and (not false) false))))
(assert (= |0_CONTROL-FORWARDING_a_GigabitEthernet0/1|
   (or (and false false)
       (and (not false)
            true
            |0_a_BGP_IMPORT_GigabitEthernet0/1_choice|
            (= |0_a_OVERALL_BEST_None_prefixLength|
               |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
            true
            (= |0_a_OVERALL_BEST_None_localPref|
               |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref|)
            (= |0_a_OVERALL_BEST_None_metric|
               |0_a_BGP_IMPORT_GigabitEthernet0/1_metric|)
            (= |0_a_OVERALL_BEST_None_med|
               |0_a_BGP_IMPORT_GigabitEthernet0/1_med|)
            true
            true
            (= |0_a_OVERALL_BEST_None_routerID| 84215045)
            true
            true
            true
            true
            true))))
(assert (=> (and true
         |0_b_BGP_IMPORT_GigabitEthernet0/1_choice|
         (= |0_b_OVERALL_BEST_None_prefixLength|
            |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
         true
         (= |0_b_OVERALL_BEST_None_localPref|
            |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref|)
         (= |0_b_OVERALL_BEST_None_metric|
            |0_b_BGP_IMPORT_GigabitEthernet0/1_metric|)
         (= |0_b_OVERALL_BEST_None_med| |0_b_BGP_IMPORT_GigabitEthernet0/1_med|)
         true
         true
         (= |0_b_OVERALL_BEST_None_routerID| 84215045)
         true
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_b_GigabitEthernet0/1|))
(assert (=> (and true
         |0_b_BGP_IMPORT_GigabitEthernet0/2_choice|
         (= |0_b_OVERALL_BEST_None_prefixLength|
            |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
         true
         (= |0_b_OVERALL_BEST_None_localPref|
            |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref|)
         (= |0_b_OVERALL_BEST_None_metric|
            |0_b_BGP_IMPORT_GigabitEthernet0/2_metric|)
         (= |0_b_OVERALL_BEST_None_med| |0_b_BGP_IMPORT_GigabitEthernet0/2_med|)
         true
         true
         (= |0_b_OVERALL_BEST_None_routerID| 16843009)
         true
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_b_GigabitEthernet0/2|))
(assert (= |0_CONTROL-FORWARDING_b_GigabitEthernet0/2|
   (or (and false false)
       (and (not false)
            true
            |0_b_BGP_IMPORT_GigabitEthernet0/2_choice|
            (= |0_b_OVERALL_BEST_None_prefixLength|
               |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
            true
            (= |0_b_OVERALL_BEST_None_localPref|
               |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref|)
            (= |0_b_OVERALL_BEST_None_metric|
               |0_b_BGP_IMPORT_GigabitEthernet0/2_metric|)
            (= |0_b_OVERALL_BEST_None_med|
               |0_b_BGP_IMPORT_GigabitEthernet0/2_med|)
            true
            true
            (= |0_b_OVERALL_BEST_None_routerID| 16843009)
            true
            true
            true
            true
            true))))
(assert (= |0_CONTROL-FORWARDING_b_GigabitEthernet0/1|
   (or (and false false)
       (and (not false)
            true
            |0_b_BGP_IMPORT_GigabitEthernet0/1_choice|
            (= |0_b_OVERALL_BEST_None_prefixLength|
               |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
            true
            (= |0_b_OVERALL_BEST_None_localPref|
               |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref|)
            (= |0_b_OVERALL_BEST_None_metric|
               |0_b_BGP_IMPORT_GigabitEthernet0/1_metric|)
            (= |0_b_OVERALL_BEST_None_med|
               |0_b_BGP_IMPORT_GigabitEthernet0/1_med|)
            true
            true
            (= |0_b_OVERALL_BEST_None_routerID| 84215045)
            true
            true
            true
            true
            true))))
(assert (= |0_CONTROL-FORWARDING_b_GigabitEthernet0/0|
   (or (and false false) (and (not false) false))))
(assert (= |0_CONTROL-FORWARDING_s_GigabitEthernet0/1|
   (or (and false false) (and (not false) false))))
(assert (= |0_CONTROL-FORWARDING_s_GigabitEthernet0/0|
   (or (and false false) (and (not false) false))))
(assert (=> (and true
         |0_d_BGP_IMPORT_GigabitEthernet0/1_choice|
         (= |0_d_OVERALL_BEST_None_prefixLength|
            |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
         (= |0_d_OVERALL_BEST_None_adminDist| 20)
         (= |0_d_OVERALL_BEST_None_localPref|
            |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref|)
         (= |0_d_OVERALL_BEST_None_metric|
            |0_d_BGP_IMPORT_GigabitEthernet0/1_metric|)
         (= |0_d_OVERALL_BEST_None_med| |0_d_BGP_IMPORT_GigabitEthernet0/1_med|)
         true
         true
         (= |0_d_OVERALL_BEST_None_routerID| 33686018)
         (= |0_d_OVERALL_BEST_None_history| #b0)
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_d_GigabitEthernet0/1|))
(assert (=> (and true
         |0_d_BGP_IMPORT_GigabitEthernet0/2_choice|
         (= |0_d_OVERALL_BEST_None_prefixLength|
            |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
         (= |0_d_OVERALL_BEST_None_adminDist| 20)
         (= |0_d_OVERALL_BEST_None_localPref|
            |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref|)
         (= |0_d_OVERALL_BEST_None_metric|
            |0_d_BGP_IMPORT_GigabitEthernet0/2_metric|)
         (= |0_d_OVERALL_BEST_None_med| |0_d_BGP_IMPORT_GigabitEthernet0/2_med|)
         true
         true
         (= |0_d_OVERALL_BEST_None_routerID| 67372036)
         (= |0_d_OVERALL_BEST_None_history| #b0)
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_d_GigabitEthernet0/2|))
(assert (=> (and true
         |0_d_BGP_IMPORT_GigabitEthernet0/0_choice|
         (= |0_d_OVERALL_BEST_None_prefixLength|
            |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
         (= |0_d_OVERALL_BEST_None_adminDist| 20)
         (= |0_d_OVERALL_BEST_None_localPref|
            |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref|)
         (= |0_d_OVERALL_BEST_None_metric|
            |0_d_BGP_IMPORT_GigabitEthernet0/0_metric|)
         (= |0_d_OVERALL_BEST_None_med| |0_d_BGP_IMPORT_GigabitEthernet0/0_med|)
         true
         true
         (= |0_d_OVERALL_BEST_None_routerID| 16843009)
         (= |0_d_OVERALL_BEST_None_history| #b0)
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_d_GigabitEthernet0/0|))
(assert (= |0_CONTROL-FORWARDING_d_GigabitEthernet0/1|
   (or (and false false)
       (and (not false)
            true
            |0_d_BGP_IMPORT_GigabitEthernet0/1_choice|
            (= |0_d_OVERALL_BEST_None_prefixLength|
               |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
            (= |0_d_OVERALL_BEST_None_adminDist| 20)
            (= |0_d_OVERALL_BEST_None_localPref|
               |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref|)
            (= |0_d_OVERALL_BEST_None_metric|
               |0_d_BGP_IMPORT_GigabitEthernet0/1_metric|)
            (= |0_d_OVERALL_BEST_None_med|
               |0_d_BGP_IMPORT_GigabitEthernet0/1_med|)
            true
            true
            (= |0_d_OVERALL_BEST_None_routerID| 33686018)
            (= |0_d_OVERALL_BEST_None_history| #b0)
            true
            true
            true
            true))))
(assert (= |0_CONTROL-FORWARDING_d_GigabitEthernet0/0|
   (or (and false false)
       (and (not false)
            true
            |0_d_BGP_IMPORT_GigabitEthernet0/0_choice|
            (= |0_d_OVERALL_BEST_None_prefixLength|
               |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
            (= |0_d_OVERALL_BEST_None_adminDist| 20)
            (= |0_d_OVERALL_BEST_None_localPref|
               |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref|)
            (= |0_d_OVERALL_BEST_None_metric|
               |0_d_BGP_IMPORT_GigabitEthernet0/0_metric|)
            (= |0_d_OVERALL_BEST_None_med|
               |0_d_BGP_IMPORT_GigabitEthernet0/0_med|)
            true
            true
            (= |0_d_OVERALL_BEST_None_routerID| 16843009)
            (= |0_d_OVERALL_BEST_None_history| #b0)
            true
            true
            true
            true))))
(assert (= |0_CONTROL-FORWARDING_d_Loopback0|
   (or (and false false) (and (not false) false))))
(assert (= |0_CONTROL-FORWARDING_d_GigabitEthernet0/2|
   (or (and false false)
       (and (not false)
            true
            |0_d_BGP_IMPORT_GigabitEthernet0/2_choice|
            (= |0_d_OVERALL_BEST_None_prefixLength|
               |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
            (= |0_d_OVERALL_BEST_None_adminDist| 20)
            (= |0_d_OVERALL_BEST_None_localPref|
               |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref|)
            (= |0_d_OVERALL_BEST_None_metric|
               |0_d_BGP_IMPORT_GigabitEthernet0/2_metric|)
            (= |0_d_OVERALL_BEST_None_med|
               |0_d_BGP_IMPORT_GigabitEthernet0/2_med|)
            true
            true
            (= |0_d_OVERALL_BEST_None_routerID| 67372036)
            (= |0_d_OVERALL_BEST_None_history| #b0)
            true
            true
            true
            true))))
(assert (=> (and true
         |0_x_BGP_IMPORT_GigabitEthernet0/0_choice|
         (= |0_x_OVERALL_BEST_None_prefixLength|
            |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
         true
         (= |0_x_OVERALL_BEST_None_localPref|
            |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref|)
         (= |0_x_OVERALL_BEST_None_metric|
            |0_x_BGP_IMPORT_GigabitEthernet0/0_metric|)
         (= |0_x_OVERALL_BEST_None_med| |0_x_BGP_IMPORT_GigabitEthernet0/0_med|)
         true
         true
         (= |0_x_OVERALL_BEST_None_routerID| 84215045)
         true
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_x_GigabitEthernet0/0|))
(assert (=> (and true
         |0_x_BGP_IMPORT_GigabitEthernet0/2_choice|
         (= |0_x_OVERALL_BEST_None_prefixLength|
            |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
         true
         (= |0_x_OVERALL_BEST_None_localPref|
            |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref|)
         (= |0_x_OVERALL_BEST_None_metric|
            |0_x_BGP_IMPORT_GigabitEthernet0/2_metric|)
         (= |0_x_OVERALL_BEST_None_med| |0_x_BGP_IMPORT_GigabitEthernet0/2_med|)
         true
         true
         (= |0_x_OVERALL_BEST_None_routerID| 67372036)
         true
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_x_GigabitEthernet0/2|))
(assert (=> (and true
         |0_x_BGP_IMPORT_GigabitEthernet0/1_choice|
         (= |0_x_OVERALL_BEST_None_prefixLength|
            |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
         true
         (= |0_x_OVERALL_BEST_None_localPref|
            |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref|)
         (= |0_x_OVERALL_BEST_None_metric|
            |0_x_BGP_IMPORT_GigabitEthernet0/1_metric|)
         (= |0_x_OVERALL_BEST_None_med| |0_x_BGP_IMPORT_GigabitEthernet0/1_med|)
         true
         true
         (= |0_x_OVERALL_BEST_None_routerID| 33686018)
         true
         true
         true
         true
         true)
    |0_CONTROL-FORWARDING_x_GigabitEthernet0/1|))
(assert (= |0_CONTROL-FORWARDING_x_GigabitEthernet0/2|
   (or (and false false)
       (and (not false)
            true
            |0_x_BGP_IMPORT_GigabitEthernet0/2_choice|
            (= |0_x_OVERALL_BEST_None_prefixLength|
               |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength|)
            true
            (= |0_x_OVERALL_BEST_None_localPref|
               |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref|)
            (= |0_x_OVERALL_BEST_None_metric|
               |0_x_BGP_IMPORT_GigabitEthernet0/2_metric|)
            (= |0_x_OVERALL_BEST_None_med|
               |0_x_BGP_IMPORT_GigabitEthernet0/2_med|)
            true
            true
            (= |0_x_OVERALL_BEST_None_routerID| 67372036)
            true
            true
            true
            true
            true))))
(assert (= |0_CONTROL-FORWARDING_x_GigabitEthernet0/1|
   (or (and false false)
       (and (not false)
            true
            |0_x_BGP_IMPORT_GigabitEthernet0/1_choice|
            (= |0_x_OVERALL_BEST_None_prefixLength|
               |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength|)
            true
            (= |0_x_OVERALL_BEST_None_localPref|
               |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref|)
            (= |0_x_OVERALL_BEST_None_metric|
               |0_x_BGP_IMPORT_GigabitEthernet0/1_metric|)
            (= |0_x_OVERALL_BEST_None_med|
               |0_x_BGP_IMPORT_GigabitEthernet0/1_med|)
            true
            true
            (= |0_x_OVERALL_BEST_None_routerID| 33686018)
            true
            true
            true
            true
            true))))
(assert (= |0_CONTROL-FORWARDING_x_GigabitEthernet0/0|
   (or (and false false)
       (and (not false)
            true
            |0_x_BGP_IMPORT_GigabitEthernet0/0_choice|
            (= |0_x_OVERALL_BEST_None_prefixLength|
               |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength|)
            true
            (= |0_x_OVERALL_BEST_None_localPref|
               |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref|)
            (= |0_x_OVERALL_BEST_None_metric|
               |0_x_BGP_IMPORT_GigabitEthernet0/0_metric|)
            (= |0_x_OVERALL_BEST_None_med|
               |0_x_BGP_IMPORT_GigabitEthernet0/0_med|)
            true
            true
            (= |0_x_OVERALL_BEST_None_routerID| 84215045)
            true
            true
            true
            true
            true))))
(assert (= (and (or false |0_CONTROL-FORWARDING_a_GigabitEthernet0/0|) true)
   |0_DATA-FORWARDING_a_GigabitEthernet0/0|))
(assert (= (and (or false |0_CONTROL-FORWARDING_a_GigabitEthernet0/2|) true)
   |0_DATA-FORWARDING_a_GigabitEthernet0/2|))
(assert (= (and (or false |0_CONTROL-FORWARDING_a_GigabitEthernet0/1|) true)
   |0_DATA-FORWARDING_a_GigabitEthernet0/1|))
(assert (= (and (or false |0_CONTROL-FORWARDING_b_GigabitEthernet0/2|) true)
   |0_DATA-FORWARDING_b_GigabitEthernet0/2|))
(assert (= (and (or false |0_CONTROL-FORWARDING_b_GigabitEthernet0/1|) true)
   |0_DATA-FORWARDING_b_GigabitEthernet0/1|))
(assert (= (and (or false |0_CONTROL-FORWARDING_b_GigabitEthernet0/0|) true)
   |0_DATA-FORWARDING_b_GigabitEthernet0/0|))
(assert (= (and (or false |0_CONTROL-FORWARDING_s_GigabitEthernet0/1|) true)
   |0_DATA-FORWARDING_s_GigabitEthernet0/1|))
(assert (= (and (or false |0_CONTROL-FORWARDING_s_GigabitEthernet0/0|) true)
   |0_DATA-FORWARDING_s_GigabitEthernet0/0|))
(assert (= (and (or false |0_CONTROL-FORWARDING_d_GigabitEthernet0/1|) true)
   |0_DATA-FORWARDING_d_GigabitEthernet0/1|))
(assert (= (and (or false |0_CONTROL-FORWARDING_d_GigabitEthernet0/0|) true)
   |0_DATA-FORWARDING_d_GigabitEthernet0/0|))
(assert (= (and (or false |0_CONTROL-FORWARDING_d_Loopback0|) true)
   |0_DATA-FORWARDING_d_Loopback0|))
(assert (= (and (or false |0_CONTROL-FORWARDING_d_GigabitEthernet0/2|) true)
   |0_DATA-FORWARDING_d_GigabitEthernet0/2|))
(assert (= (and (or false |0_CONTROL-FORWARDING_x_GigabitEthernet0/2|) true)
   |0_DATA-FORWARDING_x_GigabitEthernet0/2|))
(assert (= (and (or false |0_CONTROL-FORWARDING_x_GigabitEthernet0/1|) true)
   |0_DATA-FORWARDING_x_GigabitEthernet0/1|))
(assert (= (and (or false |0_CONTROL-FORWARDING_x_GigabitEthernet0/0|) true)
   |0_DATA-FORWARDING_x_GigabitEthernet0/0|))
(assert (=> (not |0_a_OVERALL_BEST_None_permitted|) (= |0_a_OVERALL_BEST_None_med| 0)))
(assert (=> (not |0_a_OVERALL_BEST_None_permitted|)
    (= |0_a_OVERALL_BEST_None_localPref| 0)))
(assert (=> (not |0_a_OVERALL_BEST_None_permitted|)
    (= |0_a_OVERALL_BEST_None_prefixLength| 0)))
(assert (=> (not |0_a_OVERALL_BEST_None_permitted|)
    (= |0_a_OVERALL_BEST_None_metric| 0)))
(assert (=> (not |0_a_OVERALL_BEST_None_permitted|) true))
(assert (=> (not |0_a_OVERALL_BEST_None_permitted|)
    (= |0_a_OVERALL_BEST_None_routerID| 0)))
(assert (=> (not |0_b_OVERALL_BEST_None_permitted|) (= |0_b_OVERALL_BEST_None_med| 0)))
(assert (=> (not |0_b_OVERALL_BEST_None_permitted|)
    (= |0_b_OVERALL_BEST_None_localPref| 0)))
(assert (=> (not |0_b_OVERALL_BEST_None_permitted|)
    (= |0_b_OVERALL_BEST_None_prefixLength| 0)))
(assert (=> (not |0_b_OVERALL_BEST_None_permitted|)
    (= |0_b_OVERALL_BEST_None_metric| 0)))
(assert (=> (not |0_b_OVERALL_BEST_None_permitted|) true))
(assert (=> (not |0_b_OVERALL_BEST_None_permitted|)
    (= |0_b_OVERALL_BEST_None_routerID| 0)))
(assert (=> (not |0_s_OVERALL_BEST_None_permitted|) (= |0_s_OVERALL_BEST_None_med| 0)))
(assert (=> (not |0_s_OVERALL_BEST_None_permitted|)
    (= |0_s_OVERALL_BEST_None_localPref| 0)))
(assert (=> (not |0_s_OVERALL_BEST_None_permitted|)
    (= |0_s_OVERALL_BEST_None_prefixLength| 0)))
(assert (=> (not |0_s_OVERALL_BEST_None_permitted|)
    (= |0_s_OVERALL_BEST_None_metric| 0)))
(assert (=> (not |0_s_OVERALL_BEST_None_permitted|) true))
(assert (=> (not |0_d_OVERALL_BEST_None_permitted|)
    (= |0_d_OVERALL_BEST_None_adminDist| 0)))
(assert (=> (not |0_d_OVERALL_BEST_None_permitted|) (= |0_d_OVERALL_BEST_None_med| 0)))
(assert (=> (not |0_d_OVERALL_BEST_None_permitted|)
    (= |0_d_OVERALL_BEST_None_localPref| 0)))
(assert (=> (not |0_d_OVERALL_BEST_None_permitted|)
    (= |0_d_OVERALL_BEST_None_prefixLength| 0)))
(assert (=> (not |0_d_OVERALL_BEST_None_permitted|)
    (= |0_d_OVERALL_BEST_None_metric| 0)))
(assert (=> (not |0_d_OVERALL_BEST_None_permitted|)
    (= |0_d_OVERALL_BEST_None_history| #b0)))
(assert (=> (not |0_d_OVERALL_BEST_None_permitted|)
    (= |0_d_OVERALL_BEST_None_routerID| 0)))
(assert (=> (not |0_d_BGP_BEST_None_permitted|) (= |0_d_BGP_BEST_None_med| 0)))
(assert (=> (not |0_d_BGP_BEST_None_permitted|) (= |0_d_BGP_BEST_None_localPref| 0)))
(assert (=> (not |0_d_BGP_BEST_None_permitted|) (= |0_d_BGP_BEST_None_prefixLength| 0)))
(assert (=> (not |0_d_BGP_BEST_None_permitted|) (= |0_d_BGP_BEST_None_metric| 0)))
(assert (=> (not |0_d_BGP_BEST_None_permitted|) (= |0_d_BGP_BEST_None_routerID| 0)))
(assert (=> (not |0_d_CONNECTED_BEST_None_permitted|)
    (= |0_d_CONNECTED_BEST_None_prefixLength| 0)))
(assert (=> (not |0_x_OVERALL_BEST_None_permitted|) (= |0_x_OVERALL_BEST_None_med| 0)))
(assert (=> (not |0_x_OVERALL_BEST_None_permitted|)
    (= |0_x_OVERALL_BEST_None_localPref| 0)))
(assert (=> (not |0_x_OVERALL_BEST_None_permitted|)
    (= |0_x_OVERALL_BEST_None_prefixLength| 0)))
(assert (=> (not |0_x_OVERALL_BEST_None_permitted|)
    (= |0_x_OVERALL_BEST_None_metric| 0)))
(assert (=> (not |0_x_OVERALL_BEST_None_permitted|) true))
(assert (=> (not |0_x_OVERALL_BEST_None_permitted|)
    (= |0_x_OVERALL_BEST_None_routerID| 0)))
(assert (=> (not |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_a_BGP_EXPORT_GigabitEthernet0/0_med| 0)))
(assert (=> (not |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_a_BGP_EXPORT_GigabitEthernet0/0_localPref| 0)))
(assert (=> (not |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_a_BGP_EXPORT_GigabitEthernet0/0_prefixLength| 0)))
(assert (=> (not |0_a_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_a_BGP_EXPORT_GigabitEthernet0/0_metric| 0)))
(assert (=> (not |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_a_BGP_IMPORT_GigabitEthernet0/0_med| 0)))
(assert (=> (not |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_a_BGP_IMPORT_GigabitEthernet0/0_localPref| 0)))
(assert (=> (not |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_a_BGP_IMPORT_GigabitEthernet0/0_prefixLength| 0)))
(assert (=> (not |0_a_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_a_BGP_IMPORT_GigabitEthernet0/0_metric| 0)))
(assert (=> (not |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_a_BGP_EXPORT_GigabitEthernet0/1_med| 0)))
(assert (=> (not |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_a_BGP_EXPORT_GigabitEthernet0/1_localPref| 0)))
(assert (=> (not |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_a_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 0)))
(assert (=> (not |0_a_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_a_BGP_EXPORT_GigabitEthernet0/1_metric| 0)))
(assert (=> (not |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_a_BGP_IMPORT_GigabitEthernet0/1_med| 0)))
(assert (=> (not |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_a_BGP_IMPORT_GigabitEthernet0/1_localPref| 0)))
(assert (=> (not |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_a_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 0)))
(assert (=> (not |0_a_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_a_BGP_IMPORT_GigabitEthernet0/1_metric| 0)))
(assert (=> (not |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_b_BGP_EXPORT_GigabitEthernet0/2_med| 0)))
(assert (=> (not |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_b_BGP_EXPORT_GigabitEthernet0/2_localPref| 0)))
(assert (=> (not |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_b_BGP_EXPORT_GigabitEthernet0/2_prefixLength| 0)))
(assert (=> (not |0_b_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_b_BGP_EXPORT_GigabitEthernet0/2_metric| 0)))
(assert (=> (not |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_b_BGP_IMPORT_GigabitEthernet0/2_med| 0)))
(assert (=> (not |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_b_BGP_IMPORT_GigabitEthernet0/2_localPref| 0)))
(assert (=> (not |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_b_BGP_IMPORT_GigabitEthernet0/2_prefixLength| 0)))
(assert (=> (not |0_b_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_b_BGP_IMPORT_GigabitEthernet0/2_metric| 0)))
(assert (=> (not |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_b_BGP_EXPORT_GigabitEthernet0/1_med| 0)))
(assert (=> (not |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_b_BGP_EXPORT_GigabitEthernet0/1_localPref| 0)))
(assert (=> (not |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_b_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 0)))
(assert (=> (not |0_b_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_b_BGP_EXPORT_GigabitEthernet0/1_metric| 0)))
(assert (=> (not |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_b_BGP_IMPORT_GigabitEthernet0/1_med| 0)))
(assert (=> (not |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_b_BGP_IMPORT_GigabitEthernet0/1_localPref| 0)))
(assert (=> (not |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_b_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 0)))
(assert (=> (not |0_b_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_b_BGP_IMPORT_GigabitEthernet0/1_metric| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/1_med| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/1_localPref| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/1_metric| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/1_med| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/1_localPref| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/1_metric| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/0_med| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/0_localPref| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/0_prefixLength| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/0_metric| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/0_med| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/0_localPref| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/0_prefixLength| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/0_metric| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/2_med| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/2_localPref| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/2_prefixLength| 0)))
(assert (=> (not |0_d_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_d_BGP_EXPORT_GigabitEthernet0/2_metric| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/2_med| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/2_localPref| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/2_prefixLength| 0)))
(assert (=> (not |0_d_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_d_BGP_IMPORT_GigabitEthernet0/2_metric| 0)))
(assert (=> (not |0_d_CONNECTED_IMPORT_Loopback0_permitted|)
    (= |0_d_CONNECTED_IMPORT_Loopback0_prefixLength| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/2_med| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/2_localPref| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/2_prefixLength| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/2_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/2_metric| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/2_med| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/2_localPref| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/2_prefixLength| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/2_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/2_metric| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/1_med| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/1_localPref| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/1_prefixLength| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/1_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/1_metric| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/1_med| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/1_localPref| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/1_prefixLength| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/1_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/1_metric| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/0_med| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/0_localPref| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/0_prefixLength| 0)))
(assert (=> (not |0_x_BGP_EXPORT_GigabitEthernet0/0_permitted|)
    (= |0_x_BGP_EXPORT_GigabitEthernet0/0_metric| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/0_med| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/0_localPref| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/0_prefixLength| 0)))
(assert (=> (not |0_x_BGP_IMPORT_GigabitEthernet0/0_permitted|)
    (= |0_x_BGP_IMPORT_GigabitEthernet0/0_metric| 0)))
(assert (and (or (= (bvand |0_dst-ip| #xffffffff) (bvand #x05050505 #xffffffff)))
     (not or)))
(assert (= |0__reachable_a| (> |0__reachable-id_a| 0)))
(assert (>= |0__reachable-id_a| 0))
(assert (= |0__reachable_b| (> |0__reachable-id_b| 0)))
(assert (>= |0__reachable-id_b| 0))
(assert (= |0__reachable_s| (> |0__reachable-id_s| 0)))
(assert (>= |0__reachable-id_s| 0))
(assert (= |0__reachable_d| (> |0__reachable-id_d| 0)))
(assert (>= |0__reachable-id_d| 0))
(assert (= |0__reachable_x| (> |0__reachable-id_x| 0)))
(assert (>= |0__reachable-id_x| 0))
(assert (let ((a!1 (and true
                (=> (and |0_DATA-FORWARDING_a_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_x| 0))
                    (> |0__reachable-id_a| |0__reachable-id_x|))
                (=> (and |0_DATA-FORWARDING_a_GigabitEthernet0/2|
                         true
                         (> |0__reachable-id_s| 0))
                    (> |0__reachable-id_a| |0__reachable-id_s|))
                (=> (and |0_DATA-FORWARDING_a_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_d| 0))
                    (> |0__reachable-id_a| |0__reachable-id_d|)))))
(let ((a!2 (ite (or false
                    (and |0_DATA-FORWARDING_a_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_x| 0))
                    (and |0_DATA-FORWARDING_a_GigabitEthernet0/2|
                         true
                         (> |0__reachable-id_s| 0))
                    (and |0_DATA-FORWARDING_a_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_d| 0)))
                a!1
                (= |0__reachable-id_a| 0))))
  (ite (or false false) (= |0__reachable-id_a| 1) a!2))))
(assert (let ((a!1 (and true
                (=> (and |0_DATA-FORWARDING_b_GigabitEthernet0/2|
                         true
                         (> |0__reachable-id_x| 0))
                    (> |0__reachable-id_b| |0__reachable-id_x|))
                (=> (and |0_DATA-FORWARDING_b_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_d| 0))
                    (> |0__reachable-id_b| |0__reachable-id_d|))
                (=> (and |0_DATA-FORWARDING_b_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_s| 0))
                    (> |0__reachable-id_b| |0__reachable-id_s|)))))
(let ((a!2 (ite (or false
                    (and |0_DATA-FORWARDING_b_GigabitEthernet0/2|
                         true
                         (> |0__reachable-id_x| 0))
                    (and |0_DATA-FORWARDING_b_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_d| 0))
                    (and |0_DATA-FORWARDING_b_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_s| 0)))
                a!1
                (= |0__reachable-id_b| 0))))
  (ite (or false false) (= |0__reachable-id_b| 1) a!2))))
(assert (let ((a!1 (and true
                (=> (and |0_DATA-FORWARDING_s_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_b| 0))
                    (> |0__reachable-id_s| |0__reachable-id_b|))
                (=> (and |0_DATA-FORWARDING_s_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_a| 0))
                    (> |0__reachable-id_s| |0__reachable-id_a|)))))
(let ((a!2 (ite (or false
                    (and |0_DATA-FORWARDING_s_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_b| 0))
                    (and |0_DATA-FORWARDING_s_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_a| 0)))
                a!1
                (= |0__reachable-id_s| 0))))
  (ite (or false false) (= |0__reachable-id_s| 1) a!2))))
(assert (let ((a!1 (and true
                (=> (and |0_DATA-FORWARDING_d_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_a| 0))
                    (> |0__reachable-id_d| |0__reachable-id_a|))
                (=> (and |0_DATA-FORWARDING_d_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_x| 0))
                    (> |0__reachable-id_d| |0__reachable-id_x|))
                (=> (and |0_DATA-FORWARDING_d_GigabitEthernet0/2|
                         true
                         (> |0__reachable-id_b| 0))
                    (> |0__reachable-id_d| |0__reachable-id_b|)))))
(let ((a!2 (ite (or false
                    (and |0_DATA-FORWARDING_d_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_a| 0))
                    (and |0_DATA-FORWARDING_d_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_x| 0))
                    (and |0_DATA-FORWARDING_d_GigabitEthernet0/2|
                         true
                         (> |0__reachable-id_b| 0)))
                a!1
                (= |0__reachable-id_d| 0))))
  (ite (or false
           (and |0_DATA-FORWARDING_d_Loopback0| true)
           false
           (and |0_d_CONNECTED_BEST_None_permitted| (= |0_dst-ip| #x0a001902))
           (and |0_d_CONNECTED_BEST_None_permitted| (= |0_dst-ip| #x0a000f02))
           (and |0_d_CONNECTED_BEST_None_permitted| (= |0_dst-ip| #x05050505))
           (and |0_d_CONNECTED_BEST_None_permitted| (= |0_dst-ip| #x0a002d02)))
       (= |0__reachable-id_d| 1)
       a!2))))
(assert (let ((a!1 (and true
                (=> (and |0_DATA-FORWARDING_x_GigabitEthernet0/2|
                         true
                         (> |0__reachable-id_b| 0))
                    (> |0__reachable-id_x| |0__reachable-id_b|))
                (=> (and |0_DATA-FORWARDING_x_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_a| 0))
                    (> |0__reachable-id_x| |0__reachable-id_a|))
                (=> (and |0_DATA-FORWARDING_x_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_d| 0))
                    (> |0__reachable-id_x| |0__reachable-id_d|)))))
(let ((a!2 (ite (or false
                    (and |0_DATA-FORWARDING_x_GigabitEthernet0/2|
                         true
                         (> |0__reachable-id_b| 0))
                    (and |0_DATA-FORWARDING_x_GigabitEthernet0/1|
                         true
                         (> |0__reachable-id_a| 0))
                    (and |0_DATA-FORWARDING_x_GigabitEthernet0/0|
                         true
                         (> |0__reachable-id_d| 0)))
                a!1
                (= |0__reachable-id_x| 0))))
  (ite (or false false) (= |0__reachable-id_x| 1) a!2))))
(assert (not (and true |0__reachable_x|)))
(assert (=> (= (bvand |0_dst-ip| #xfffffffc) (bvand #x0a001900 #xfffffffc))
    (= |0_FAILED-EDGE_a_d| 0)))
(assert (=> (= (bvand |0_dst-ip| #xfffffffc) (bvand #x0a000f00 #xfffffffc))
    (= |0_FAILED-EDGE_d_x| 0)))
(assert (= |0_FAILED-EDGE_d_Loopback0| 0))
(assert (=> (= (bvand |0_dst-ip| #xfffffffc) (bvand #x0a002d00 #xfffffffc))
    (= |0_FAILED-EDGE_b_d| 0)))

(check-sat)
;(get-model)
