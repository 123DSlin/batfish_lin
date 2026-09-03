package org.batfish.minesweeper.symbolicroute;

import static org.hamcrest.Matchers.equalTo;
import static org.junit.Assert.assertThat;

import com.microsoft.z3.Context;
import org.batfish.common.util.BatfishObjectMapper;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.JUnit4;

/** Tests persistence and solver-context-independent reconstruction of Boolean route guards. */
@RunWith(JUnit4.class)
public final class BooleanGuardAstTest {

  @Test
  public void testCanonicalAssociativeFormIsOrderIndependentAndDeduplicated() {
    BooleanGuardAst a = BooleanGuardAst.variable("a");
    BooleanGuardAst b = BooleanGuardAst.variable("b");

    assertThat(
        BooleanGuardAst.and(a, BooleanGuardAst.and(b, a)), equalTo(BooleanGuardAst.and(b, a)));
    assertThat(BooleanGuardAst.or(a, BooleanGuardAst.or(b, a)), equalTo(BooleanGuardAst.or(b, a)));
  }

  @Test
  public void testJsonRoundTripRebuildsEquivalentGuardInNewContext() {
    BooleanGuardAst persisted;
    try (Context producerContext = new Context()) {
      Z3RouteGuardFactory producer = new Z3RouteGuardFactory(producerContext);
      persisted =
          producer
              .variable("a")
              .and(producer.variable("b").not())
              .or(producer.variable("c"))
              .simplify()
              .getAst();
    }

    BooleanGuardAst decoded = BatfishObjectMapper.clone(persisted, BooleanGuardAst.class);
    assertThat(decoded, equalTo(persisted));
    try (Context consumerContext = new Context()) {
      Z3RouteGuardFactory consumer = new Z3RouteGuardFactory(consumerContext);
      RouteGuard rebuilt = consumer.fromAst(decoded);
      RouteGuard expected =
          consumer.variable("a").and(consumer.variable("b").not()).or(consumer.variable("c"));
      assertThat(rebuilt.isEquivalentTo(expected), equalTo(true));
    }
  }
}
