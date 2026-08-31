package org.batfish.minesweeper.symbolicsr;

import static org.batfish.datamodel.Configuration.DEFAULT_VRF_NAME;
import static org.hamcrest.Matchers.equalTo;
import static org.hamcrest.Matchers.hasSize;
import static org.junit.Assert.assertThat;

import com.google.common.collect.ImmutableList;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.ImmutableSet;
import com.microsoft.z3.Context;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConfigurationFormat;
import org.batfish.datamodel.Ip6;
import org.batfish.datamodel.NetworkFactory;
import org.batfish.datamodel.Prefix;
import org.batfish.datamodel.sr.SegmentRoutingConfig;
import org.batfish.datamodel.sr.SrGlobalBlock;
import org.batfish.datamodel.sr.SrLabelRange;
import org.batfish.datamodel.sr.SrPrefix;
import org.batfish.datamodel.sr.SrSidBinding;
import org.batfish.datamodel.sr.SrSidBindingKey;
import org.batfish.datamodel.sr.SrSidValue;
import org.batfish.minesweeper.symbolicroute.LinkFailureKey;
import org.batfish.minesweeper.symbolicroute.Z3RouteGuardFactory;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests MPLS label-scope validation independently of the IS-IS integration fixture. */
@RunWith(JUnit4.class)
public final class MplsLabelPlanResolverTest {
  private static final Z3RouteGuardFactory GUARDS = new Z3RouteGuardFactory(new Context());

  @Test
  public void testAbsolutePrefixLabelIsFixed() {
    SrSidBinding binding = prefixBinding(SrSidValue.mplsLabel(16001L), ImmutableSet.of());
    GuardedSegmentList segments =
        segments(new GuardedSidEntry("r2", "default", binding, GUARDS.trueGuard()));
    MplsLabelPlan plan = new MplsLabelPlanResolver(ImmutableMap.of()).resolve(segments).get();
    assertThat(plan.getTopFirstInstructions(), hasSize(1));
    MplsLabelInstruction instruction = plan.getTopFirstInstructions().get(0);
    assertThat(instruction.getScope(), equalTo(MplsLabelInstruction.Scope.FIXED_LABEL));
    assertThat(instruction.getResolvedLabel(), equalTo(SrSidValue.mplsLabel(16001L)));
  }

  @Test
  public void testSrv6AndLocalPrefixFailClosed() {
    assertThat(
        new MplsLabelPlanResolver(ImmutableMap.of())
            .resolve(
                segments(
                    new GuardedSidEntry(
                        "r2",
                        "default",
                        prefixBinding(SrSidValue.srv6(Ip6.parse("2001:db8::1")), ImmutableSet.of()),
                        GUARDS.trueGuard())))
            .isPresent(),
        equalTo(false));
    assertThat(
        new MplsLabelPlanResolver(ImmutableMap.of())
            .resolve(
                segments(
                    new GuardedSidEntry(
                        "r2",
                        "default",
                        prefixBinding(
                            SrSidValue.mplsLabel(16001L), ImmutableSet.of(SrSidBinding.Flag.LOCAL)),
                        GUARDS.trueGuard())))
            .isPresent(),
        equalTo(false));
  }

  @Test
  public void testAdjacencyIndexRequiresOwnerSrlb() {
    SrSidBindingKey key =
        new SrSidBindingKey("r1", "default", SrSidBindingKey.Type.ADJACENCY, 0, null, "Eth0", null);
    SrSidBinding binding =
        new SrSidBinding(key, SrSidValue.mplsIndex(4L), ImmutableSet.of(SrSidBinding.Flag.LOCAL));
    GuardedSidEntry entry =
        new GuardedSidEntry(
            "r1",
            "default",
            binding,
            GUARDS.trueGuard(),
            LinkFailureKey.of("r1", "r2"),
            new SymbolicAdjacencyEndpoint("r2", "default", "Eth1"));
    Configuration owner =
        new NetworkFactory()
            .configurationBuilder()
            .setHostname("r1")
            .setConfigurationFormat(ConfigurationFormat.CISCO_IOS)
            .build();
    owner.setSegmentRoutingConfig(
        new SegmentRoutingConfig(
            ImmutableSet.of(SegmentRoutingConfig.DataPlane.MPLS),
            SrGlobalBlock.of(ImmutableList.of(SrLabelRange.of(16000L, 23999L))),
            null,
            ImmutableMap.of()));
    assertThat(
        new MplsLabelPlanResolver(ImmutableMap.of("r1", owner))
            .resolve(segments(entry))
            .isPresent(),
        equalTo(false));
  }

  private static SrSidBinding prefixBinding(SrSidValue sid, ImmutableSet<SrSidBinding.Flag> flags) {
    return new SrSidBinding(
        new SrSidBindingKey(
            "r1",
            DEFAULT_VRF_NAME,
            SrSidBindingKey.Type.PREFIX,
            0,
            SrPrefix.ipv4(Prefix.parse("1.1.1.1/32")),
            null,
            null),
        sid,
        flags);
  }

  private static GuardedSegmentList segments(GuardedSidEntry entry) {
    return new GuardedSegmentList(
        ImmutableList.of(entry), GUARDS.trueGuard(), "r1", DEFAULT_VRF_NAME);
  }
}
