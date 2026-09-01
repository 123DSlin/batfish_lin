package org.batfish.minesweeper.symbolicroute;

import static java.util.Objects.requireNonNull;

import com.google.common.collect.ImmutableList;
import java.util.Comparator;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AnnotatedRoute;
import org.batfish.datamodel.ConcreteInterfaceAddress;
import org.batfish.datamodel.Configuration;
import org.batfish.datamodel.ConnectedRoute;
import org.batfish.datamodel.ConnectedRouteMetadata;
import org.batfish.datamodel.Interface;
import org.batfish.datamodel.LocalRoute;
import org.batfish.datamodel.Prefix;

/** Lifts Batfish connected/local route initialization over canonical interface guards. */
public final class BatfishInterfaceRouteInitializer {

  private BatfishInterfaceRouteInitializer() {}

  /** Builds exactly the configured connected/local seeds produced for active Batfish interfaces. */
  @Nonnull
  public static ImmutableList<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> build(
      Configuration configuration,
      TopologyLinkGuards topologyGuards,
      Z3RouteGuardFactory guardFactory) {
    requireNonNull(configuration, "configuration must be provided");
    requireNonNull(topologyGuards, "topologyGuards must be provided");
    requireNonNull(guardFactory, "guardFactory must be provided");
    ImmutableList.Builder<SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>>> seeds =
        ImmutableList.builder();
    configuration.getAllInterfaces().values().stream()
        .filter(Interface::getActive)
        .sorted(Comparator.comparing(Interface::getName))
        .forEach(
            iface ->
                iface.getAllConcreteAddresses().stream()
                    .sorted()
                    .forEach(
                        address -> {
                          ConnectedRouteMetadata metadata = iface.getAddressMetadata().get(address);
                          RouteGuard guard =
                              interfaceGuard(configuration, iface, topologyGuards, guardFactory);
                          LinkFailureKey linkFailureKey =
                              topologyGuards.getKey(configuration.getHostname(), iface.getName());
                          if (shouldGenerateConnected(metadata)) {
                            seeds.add(
                                seed(
                                    "connected",
                                    configuration,
                                    iface,
                                    address,
                                    connectedRoute(address, iface.getName(), metadata),
                                    guard,
                                    linkFailureKey));
                          }
                          if (shouldGenerateLocal(address, metadata)) {
                            seeds.add(
                                seed(
                                    "local",
                                    configuration,
                                    iface,
                                    address,
                                    localRoute(address, iface.getName(), metadata),
                                    guard,
                                    linkFailureKey));
                          }
                        }));
    return seeds.build();
  }

  private static boolean shouldGenerateConnected(@Nullable ConnectedRouteMetadata metadata) {
    return metadata == null
        || metadata.getGenerateConnectedRoute() == null
        || metadata.getGenerateConnectedRoute();
  }

  private static boolean shouldGenerateLocal(
      ConcreteInterfaceAddress address, @Nullable ConnectedRouteMetadata metadata) {
    return metadata != null && metadata.getGenerateLocalRoute() != null
        ? metadata.getGenerateLocalRoute()
        : address.getNetworkBits() < Prefix.MAX_PREFIX_LENGTH;
  }

  private static ConnectedRoute connectedRoute(
      ConcreteInterfaceAddress address,
      String interfaceName,
      @Nullable ConnectedRouteMetadata metadata) {
    ConnectedRoute.Builder builder =
        ConnectedRoute.builder().setNetwork(address.getPrefix()).setNextHopInterface(interfaceName);
    applyMetadata(builder, metadata);
    return builder.build();
  }

  private static LocalRoute localRoute(
      ConcreteInterfaceAddress address,
      String interfaceName,
      @Nullable ConnectedRouteMetadata metadata) {
    LocalRoute.Builder builder =
        LocalRoute.builder()
            .setNetwork(address.getIp().toPrefix())
            .setSourcePrefixLength(address.getNetworkBits())
            .setNextHopInterface(interfaceName);
    applyMetadata(builder, metadata);
    return builder.build();
  }

  private static void applyMetadata(
      org.batfish.datamodel.AbstractRouteBuilder<?, ?> builder,
      @Nullable ConnectedRouteMetadata metadata) {
    if (metadata == null) {
      return;
    }
    if (metadata.getAdmin() != null) {
      builder.setAdmin(metadata.getAdmin());
    }
    if (metadata.getTag() != null) {
      builder.setTag(metadata.getTag());
    }
  }

  private static SymbolicRouteSeed<AnnotatedRoute<AbstractRoute>> seed(
      String protocol,
      Configuration configuration,
      Interface iface,
      ConcreteInterfaceAddress address,
      AbstractRoute route,
      RouteGuard guard,
      @Nullable LinkFailureKey linkFailureKey) {
    return new SymbolicRouteSeed<>(
        protocol + ":" + configuration.getHostname() + ":" + iface.getName() + ":" + address,
        configuration.getHostname(),
        new AnnotatedRoute<>(route, iface.getVrfName()),
        guard,
        linkFailureKey);
  }

  private static RouteGuard interfaceGuard(
      Configuration configuration,
      Interface iface,
      TopologyLinkGuards topologyGuards,
      Z3RouteGuardFactory guardFactory) {
    RouteGuard inferred = topologyGuards.getGuard(configuration.getHostname(), iface.getName());
    return inferred == null ? guardFactory.trueGuard() : inferred;
  }
}
