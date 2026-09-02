package org.batfish.minesweeper.symbolicroute;

import static com.google.common.base.MoreObjects.firstNonNull;
import static java.nio.charset.StandardCharsets.UTF_8;
import static java.util.Objects.requireNonNull;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.google.common.collect.ImmutableList;
import com.google.common.hash.Hashing;
import java.io.IOException;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import javax.annotation.Nonnull;
import javax.annotation.Nullable;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.datamodel.AbstractRoute;
import org.batfish.datamodel.AbstractRouteDecorator;
import org.batfish.datamodel.AnnotatedRoute;

/** Versioned, lossless transport view of one converged symbolic control plane. */
public final class SymbolicControlPlaneExport {

  public static final String SCHEMA_NAME = "batfish-minesweeper-symbolic-control-plane";
  public static final int SCHEMA_VERSION = 1;

  /** Exact and display-simplified representations of one semantically identical guard. */
  public static final class Guard {
    @Nonnull private final String _raw;
    @Nonnull private final String _simplified;
    private final boolean _satisfiable;

    @JsonCreator
    private Guard(
        @JsonProperty("raw") String raw,
        @JsonProperty("simplified") String simplified,
        @JsonProperty("satisfiable") boolean satisfiable) {
      _raw = requireNonNull(raw, "raw guard must be provided");
      _simplified = requireNonNull(simplified, "simplified guard must be provided");
      _satisfiable = satisfiable;
    }

    private static Guard from(RouteGuard guard) {
      RouteGuard checked = requireNonNull(guard, "guard must be provided");
      return new Guard(
          checked.toString(), checked.simplifyForDisplay().toString(), checked.isSatisfiable());
    }

    @JsonProperty("raw")
    @Nonnull
    public String getRaw() {
      return _raw;
    }

    @JsonProperty("simplified")
    @Nonnull
    public String getSimplified() {
      return _simplified;
    }

    @JsonProperty("satisfiable")
    public boolean getSatisfiable() {
      return _satisfiable;
    }
  }

  /** Stable identity of one directed advertisement contribution. */
  public static final class ContributionId {
    @Nonnull private final String _messageId;
    @Nonnull private final String _sender;
    @Nonnull private final String _receiver;

    @JsonCreator
    private ContributionId(
        @JsonProperty("messageId") String messageId,
        @JsonProperty("sender") String sender,
        @JsonProperty("receiver") String receiver) {
      _messageId = requireNonNull(messageId, "messageId must be provided");
      _sender = requireNonNull(sender, "sender must be provided");
      _receiver = requireNonNull(receiver, "receiver must be provided");
    }

    private static ContributionId from(SymbolicRouteContributionId id) {
      return new ContributionId(id.getMessageId(), id.getSender(), id.getReceiver());
    }

    private String canonicalForm() {
      return lengthPrefixed(_sender) + lengthPrefixed(_receiver) + lengthPrefixed(_messageId);
    }

    @JsonProperty("messageId")
    @Nonnull
    public String getMessageId() {
      return _messageId;
    }

    @JsonProperty("sender")
    @Nonnull
    public String getSender() {
      return _sender;
    }

    @JsonProperty("receiver")
    @Nonnull
    public String getReceiver() {
      return _receiver;
    }
  }

  /** Full Batfish route payload, separated from transport identity and human formatting. */
  public static final class RoutePayload {
    @Nonnull private final String _routeType;
    @Nullable private final String _sourceVrf;
    @Nonnull private final JsonNode _attributes;

    @JsonCreator
    private RoutePayload(
        @JsonProperty("routeType") String routeType,
        @Nullable @JsonProperty("sourceVrf") String sourceVrf,
        @JsonProperty("attributes") JsonNode attributes) {
      _routeType = requireNonNull(routeType, "routeType must be provided");
      _sourceVrf = sourceVrf;
      _attributes = requireNonNull(attributes, "route attributes must be provided");
    }

    private static RoutePayload from(AbstractRouteDecorator route) {
      AbstractRoute concrete = requireNonNull(route, "route must be provided").getAbstractRoute();
      String sourceVrf =
          route instanceof AnnotatedRoute ? ((AnnotatedRoute<?>) route).getSourceVrf() : null;
      return new RoutePayload(
          concrete.getClass().getName(),
          sourceVrf,
          BatfishObjectMapper.verboseMapper().valueToTree(concrete));
    }

    @JsonProperty("routeType")
    @Nonnull
    public String getRouteType() {
      return _routeType;
    }

    @JsonProperty("sourceVrf")
    @Nullable
    public String getSourceVrf() {
      return _sourceVrf;
    }

    @JsonProperty("attributes")
    @Nonnull
    public JsonNode getAttributes() {
      return _attributes;
    }

    /** Reconstructs the exact supported Batfish route type after checking the discriminator. */
    @Nonnull
    public <R extends AbstractRoute> R decode(Class<R> expectedType) {
      Class<R> checked = requireNonNull(expectedType, "expectedType must be provided");
      if (!_routeType.equals(checked.getName())) {
        throw new IllegalArgumentException("route payload type does not match expected type");
      }
      try {
        return BatfishObjectMapper.mapper().treeToValue(_attributes, checked);
      } catch (JsonProcessingException e) {
        throw new IllegalArgumentException("invalid Batfish route payload", e);
      }
    }
  }

  /** Propagation provenance retained for one contribution rather than its aggregate candidate. */
  public static final class Provenance {
    @Nonnull private final String _originRouter;
    @Nonnull private final String _currentRouter;
    @Nullable private final String _previousRouter;
    @Nullable private final String _incomingInterface;
    @Nonnull private final ImmutableList<String> _routerPath;
    @Nullable private final String _parentMessageId;

    @JsonCreator
    private Provenance(
        @JsonProperty("originRouter") String originRouter,
        @JsonProperty("currentRouter") String currentRouter,
        @Nullable @JsonProperty("previousRouter") String previousRouter,
        @Nullable @JsonProperty("incomingInterface") String incomingInterface,
        @JsonProperty("routerPath") List<String> routerPath,
        @Nullable @JsonProperty("parentMessageId") String parentMessageId) {
      _originRouter = requireNonNull(originRouter, "originRouter must be provided");
      _currentRouter = requireNonNull(currentRouter, "currentRouter must be provided");
      _previousRouter = previousRouter;
      _incomingInterface = incomingInterface;
      _routerPath = ImmutableList.copyOf(requireNonNull(routerPath, "routerPath must be provided"));
      _parentMessageId = parentMessageId;
    }

    private static Provenance from(SymbolicRouteProvenance provenance) {
      return new Provenance(
          provenance.getOriginRouter(),
          provenance.getCurrentRouter(),
          provenance.getPreviousRouter(),
          provenance.getIncomingInterface(),
          provenance.getRouterPath(),
          provenance.getParentMessageId());
    }

    @JsonProperty("originRouter")
    @Nonnull
    public String getOriginRouter() {
      return _originRouter;
    }

    @JsonProperty("currentRouter")
    @Nonnull
    public String getCurrentRouter() {
      return _currentRouter;
    }

    @JsonProperty("previousRouter")
    @Nullable
    public String getPreviousRouter() {
      return _previousRouter;
    }

    @JsonProperty("incomingInterface")
    @Nullable
    public String getIncomingInterface() {
      return _incomingInterface;
    }

    @JsonProperty("routerPath")
    @Nonnull
    public ImmutableList<String> getRouterPath() {
      return _routerPath;
    }

    @JsonProperty("parentMessageId")
    @Nullable
    public String getParentMessageId() {
      return _parentMessageId;
    }
  }

  /** One independently guarded source of a candidate. */
  public static final class Contribution {
    @Nonnull private final ContributionId _id;
    @Nullable private final String _sessionId;
    @Nonnull private final Guard _availabilityGuard;
    @Nonnull private final Guard _selectionGuard;
    @Nonnull private final Provenance _provenance;
    @Nonnull private final ImmutableList<ContributionId> _parents;

    @JsonCreator
    private Contribution(
        @JsonProperty("id") ContributionId id,
        @Nullable @JsonProperty("sessionId") String sessionId,
        @JsonProperty("availabilityGuard") Guard availabilityGuard,
        @JsonProperty("selectionGuard") Guard selectionGuard,
        @JsonProperty("provenance") Provenance provenance,
        @Nullable @JsonProperty("parents") List<ContributionId> parents) {
      _id = requireNonNull(id, "contribution id must be provided");
      _sessionId = sessionId;
      _availabilityGuard = requireNonNull(availabilityGuard, "availabilityGuard must be provided");
      _selectionGuard = requireNonNull(selectionGuard, "selectionGuard must be provided");
      _provenance = requireNonNull(provenance, "provenance must be provided");
      _parents = ImmutableList.copyOf(firstNonNull(parents, ImmutableList.of()));
    }

    @JsonProperty("id")
    @Nonnull
    public ContributionId getId() {
      return _id;
    }

    @JsonProperty("sessionId")
    @Nullable
    public String getSessionId() {
      return _sessionId;
    }

    @JsonProperty("availabilityGuard")
    @Nonnull
    public Guard getAvailabilityGuard() {
      return _availabilityGuard;
    }

    @JsonProperty("selectionGuard")
    @Nonnull
    public Guard getSelectionGuard() {
      return _selectionGuard;
    }

    @JsonProperty("provenance")
    @Nonnull
    public Provenance getProvenance() {
      return _provenance;
    }

    @JsonProperty("parents")
    @Nonnull
    public ImmutableList<ContributionId> getParents() {
      return _parents;
    }
  }

  /** One aggregate guarded RIB candidate and each advertisement that supports it. */
  public static final class Candidate {
    @Nonnull private final String _candidateId;
    @Nonnull private final SymbolicRibRecord.Plane _plane;
    @Nonnull private final String _router;
    @Nonnull private final String _vrf;
    @Nonnull private final String _prefix;
    @Nonnull private final String _protocol;
    @Nonnull private final RoutePayload _route;
    @Nonnull private final Guard _availabilityGuard;
    @Nonnull private final Guard _selectionGuard;
    @Nonnull private final ImmutableList<Contribution> _contributions;

    @JsonCreator
    private Candidate(
        @JsonProperty("candidateId") String candidateId,
        @JsonProperty("plane") SymbolicRibRecord.Plane plane,
        @JsonProperty("router") String router,
        @JsonProperty("vrf") String vrf,
        @JsonProperty("prefix") String prefix,
        @JsonProperty("protocol") String protocol,
        @JsonProperty("route") RoutePayload route,
        @JsonProperty("availabilityGuard") Guard availabilityGuard,
        @JsonProperty("selectionGuard") Guard selectionGuard,
        @Nullable @JsonProperty("contributions") List<Contribution> contributions) {
      _candidateId = requireNonNull(candidateId, "candidateId must be provided");
      _plane = requireNonNull(plane, "plane must be provided");
      _router = requireNonNull(router, "router must be provided");
      _vrf = requireNonNull(vrf, "vrf must be provided");
      _prefix = requireNonNull(prefix, "prefix must be provided");
      _protocol = requireNonNull(protocol, "protocol must be provided");
      _route = requireNonNull(route, "route must be provided");
      _availabilityGuard = requireNonNull(availabilityGuard, "availabilityGuard must be provided");
      _selectionGuard = requireNonNull(selectionGuard, "selectionGuard must be provided");
      _contributions = ImmutableList.copyOf(firstNonNull(contributions, ImmutableList.of()));
    }

    @JsonProperty("candidateId")
    @Nonnull
    public String getCandidateId() {
      return _candidateId;
    }

    @JsonProperty("plane")
    @Nonnull
    public SymbolicRibRecord.Plane getPlane() {
      return _plane;
    }

    @JsonProperty("router")
    @Nonnull
    public String getRouter() {
      return _router;
    }

    @JsonProperty("vrf")
    @Nonnull
    public String getVrf() {
      return _vrf;
    }

    @JsonProperty("prefix")
    @Nonnull
    public String getPrefix() {
      return _prefix;
    }

    @JsonProperty("protocol")
    @Nonnull
    public String getProtocol() {
      return _protocol;
    }

    @JsonProperty("route")
    @Nonnull
    public RoutePayload getRoute() {
      return _route;
    }

    @JsonProperty("availabilityGuard")
    @Nonnull
    public Guard getAvailabilityGuard() {
      return _availabilityGuard;
    }

    @JsonProperty("selectionGuard")
    @Nonnull
    public Guard getSelectionGuard() {
      return _selectionGuard;
    }

    @JsonProperty("contributions")
    @Nonnull
    public ImmutableList<Contribution> getContributions() {
      return _contributions;
    }
  }

  @Nonnull private final String _schemaName;
  private final int _schemaVersion;
  @Nonnull private final ImmutableList<Candidate> _candidates;

  @JsonCreator
  private SymbolicControlPlaneExport(
      @JsonProperty("schemaName") String schemaName,
      @JsonProperty("schemaVersion") int schemaVersion,
      @Nullable @JsonProperty("candidates") List<Candidate> candidates) {
    _schemaName = requireNonNull(schemaName, "schemaName must be provided");
    if (!_schemaName.equals(SCHEMA_NAME) || schemaVersion != SCHEMA_VERSION) {
      throw new IllegalArgumentException("unsupported symbolic control-plane schema");
    }
    _schemaVersion = schemaVersion;
    _candidates = ImmutableList.copyOf(firstNonNull(candidates, ImmutableList.of()));
  }

  /** Captures all protocol and MAIN guarded candidates without using route strings as data. */
  @Nonnull
  public static SymbolicControlPlaneExport from(BatfishSymbolicRoutePipelineResult result) {
    BatfishSymbolicRoutePipelineResult checked = requireNonNull(result, "result must be provided");
    List<Candidate> candidates = new ArrayList<>();
    appendPlane(candidates, SymbolicRibRecord.Plane.MAIN, checked.getMainRibNetwork());
    appendPlane(candidates, SymbolicRibRecord.Plane.BGP, checked.getBgpRibNetwork());
    appendPlane(candidates, SymbolicRibRecord.Plane.ISIS_L1, checked.getIsisL1RibNetwork());
    appendPlane(candidates, SymbolicRibRecord.Plane.ISIS_L2, checked.getIsisL2RibNetwork());
    candidates.sort(
        Comparator.comparing((Candidate candidate) -> candidate.getPlane().ordinal())
            .thenComparing(Candidate::getRouter)
            .thenComparing(Candidate::getVrf)
            .thenComparing(Candidate::getPrefix)
            .thenComparing(Candidate::getCandidateId));
    return new SymbolicControlPlaneExport(SCHEMA_NAME, SCHEMA_VERSION, candidates);
  }

  private static <R extends AbstractRouteDecorator> void appendPlane(
      List<Candidate> output, SymbolicRibRecord.Plane plane, SymbolicRouteNetwork<R> network) {
    network
        .getRibs()
        .values()
        .forEach(
            rib ->
                rib.getEntries()
                    .forEach(
                        entry ->
                            output.add(candidate(plane, rib, entry, network.getDependencies()))));
  }

  private static <R extends AbstractRouteDecorator> Candidate candidate(
      SymbolicRibRecord.Plane plane,
      GuardedRib<R> rib,
      GuardedRibEntry<R> entry,
      SymbolicRoutePropagationDependencies dependencies) {
    SymbolicRoute<R> symbolic = entry.getSymbolicRoute();
    RoutePayload payload = RoutePayload.from(symbolic.getRoute());
    List<Contribution> contributions = new ArrayList<>();
    rib.getContributionEntries(symbolic.getKey())
        .forEach(
            (id, contribution) -> {
              List<ContributionId> parents = new ArrayList<>();
              dependencies
                  .getParents(id)
                  .forEach(parent -> parents.add(ContributionId.from(parent)));
              parents.sort(Comparator.comparing(ContributionId::canonicalForm));
              contributions.add(
                  new Contribution(
                      ContributionId.from(id),
                      rib.getContributionSessionId(id),
                      Guard.from(contribution.getAvailabilityGuard()),
                      Guard.from(contribution.getSelectionGuard()),
                      Provenance.from(contribution.getSymbolicRoute().getProvenance()),
                      parents));
            });
    contributions.sort(Comparator.comparing(contribution -> contribution.getId().canonicalForm()));
    String candidateId = candidateId(plane, symbolic.getKey(), payload);
    return new Candidate(
        candidateId,
        plane,
        symbolic.getKey().getRouter(),
        symbolic.getKey().getVrf(),
        symbolic.getKey().getNetwork().toString(),
        symbolic.getKey().getProtocol().toString(),
        payload,
        Guard.from(entry.getAvailabilityGuard()),
        Guard.from(entry.getSelectionGuard()),
        contributions);
  }

  private static String candidateId(
      SymbolicRibRecord.Plane plane, SymbolicRouteKey key, RoutePayload payload) {
    try {
      String canonical =
          lengthPrefixed(plane.name())
              + lengthPrefixed(key.getRouter())
              + lengthPrefixed(key.getVrf())
              + lengthPrefixed(BatfishObjectMapper.writeString(payload));
      return "candidate-v1-" + Hashing.sha256().hashString(canonical, UTF_8);
    } catch (JsonProcessingException e) {
      throw new IllegalArgumentException("failed to encode candidate identity", e);
    }
  }

  private static String lengthPrefixed(String value) {
    return value.length() + ":" + value;
  }

  @JsonProperty("schemaName")
  @Nonnull
  public String getSchemaName() {
    return _schemaName;
  }

  @JsonProperty("schemaVersion")
  public int getSchemaVersion() {
    return _schemaVersion;
  }

  @JsonProperty("candidates")
  @Nonnull
  public ImmutableList<Candidate> getCandidates() {
    return _candidates;
  }

  /** Parses and validates the schema marker and version. */
  @Nonnull
  public static SymbolicControlPlaneExport fromJson(String json) {
    try {
      return BatfishObjectMapper.mapper().readValue(json, SymbolicControlPlaneExport.class);
    } catch (IOException e) {
      throw new IllegalArgumentException("invalid symbolic control-plane JSON", e);
    }
  }

  /** Produces deterministic pretty JSON for the Java/Python integration boundary. */
  @Nonnull
  public String toJson() {
    try {
      return BatfishObjectMapper.writePrettyString(this);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("failed to serialize symbolic control plane", e);
    }
  }
}
