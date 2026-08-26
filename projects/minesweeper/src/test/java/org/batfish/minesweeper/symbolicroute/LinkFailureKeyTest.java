package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConnectedRoute;
import org.batfish.datamodel.Prefix;
import org.junit.Test;

public final class LinkFailureKeyTest {

  @Test
  public void testDirectionIndependentIdentityAndStableName() {
    LinkFailureKey forward = LinkFailureKey.of("r1", "r4");
    LinkFailureKey reverse = LinkFailureKey.of("r4", "r1");

    assertThat(forward, equalTo(reverse));
    assertThat(forward.hashCode(), equalTo(reverse.hashCode()));
    assertThat(forward.guardName(), equalTo("r1_r4"));
  }

  @Test(expected = IllegalArgumentException.class)
  public void testRejectsSelfLink() {
    LinkFailureKey.of("r1", "r1");
  }

  @Test
  public void testConnectedSeedAndBgpSessionCanShareCanonicalKey() {
    LinkFailureKey key = LinkFailureKey.of("r1", "r4");
    try (com.microsoft.z3.Context context = new com.microsoft.z3.Context()) {
      RouteGuard up = new Z3RouteGuardFactory(context).variable(key.guardName());
      SymbolicRouteSeed<AnnotatedRoute<ConnectedRoute>> seed =
          new SymbolicRouteSeed<>(
              "connected",
              "r1",
              new AnnotatedRoute<>(
                  new ConnectedRoute(Prefix.parse("192.0.14.0/30"), "Ethernet14"), "default"),
              up,
              key);
      SymbolicRouteSession session = new SymbolicRouteSession("r1-r4", "r1", "r4", up, key);

      assertThat(seed.getLinkFailureKey(), equalTo(key));
      assertThat(session.getLinkFailureKey(), equalTo(key));
    }
  }

  @Test(expected = IllegalArgumentException.class)
  public void testSessionRejectsMismatchedCanonicalKey() {
    try (com.microsoft.z3.Context context = new com.microsoft.z3.Context()) {
      new SymbolicRouteSession(
          "r1-r4",
          "r1",
          "r4",
          new Z3RouteGuardFactory(context).variable("r1_r2"),
          LinkFailureKey.of("r1", "r2"));
    }
  }
}
