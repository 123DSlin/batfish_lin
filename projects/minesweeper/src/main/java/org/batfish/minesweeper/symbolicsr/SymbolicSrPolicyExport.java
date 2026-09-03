package org.batfish.minesweeper.symbolicsr;

import static java.util.Objects.requireNonNull;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.google.common.collect.ImmutableList;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeSet;
import javax.annotation.Nonnull;
import org.batfish.common.util.BatfishObjectMapper;
import org.batfish.minesweeper.symbolicroute.LinkFailureKey;
import org.batfish.minesweeper.symbolicroute.SymbolicControlPlaneExport;

/** Versioned machine-readable export of guarded SR candidates and forwarding branches. */
public final class SymbolicSrPolicyExport {

  public static final String SCHEMA_NAME = "batfish-minesweeper-symbolic-sr-policies";
  public static final int SCHEMA_VERSION = 1;

  @Nonnull private final ImmutableList<SymbolicControlPlaneExport.GuardVariable> _guardVariables;

  @Nonnull private final ImmutableList<SymbolicSrPolicyRecord> _records;

  @JsonCreator
  private SymbolicSrPolicyExport(
      @JsonProperty("schemaName") String schemaName,
      @JsonProperty("schemaVersion") int schemaVersion,
      @JsonProperty("guardVariables") List<SymbolicControlPlaneExport.GuardVariable> guardVariables,
      @JsonProperty("records") List<SymbolicSrPolicyRecord> records) {
    if (!SCHEMA_NAME.equals(schemaName)) {
      throw new IllegalArgumentException("unsupported symbolic SR-policy schema: " + schemaName);
    }
    if (schemaVersion != SCHEMA_VERSION) {
      throw new IllegalArgumentException(
          "unsupported symbolic SR-policy schema version: " + schemaVersion);
    }
    _guardVariables =
        ImmutableList.copyOf(requireNonNull(guardVariables, "guardVariables must be provided"));
    _records = ImmutableList.copyOf(requireNonNull(records, "records must be provided"));
  }

  public static SymbolicSrPolicyExport of(
      List<SymbolicSrPolicyRecord> records,
      Map<String, LinkFailureKey> linkFailureKeysByGuardVariable) {
    Set<String> variables = new TreeSet<>();
    records.forEach(
        record -> {
          variables.addAll(record.getAvailabilityGuardAst().getVariables());
          variables.addAll(record.getSelectionGuardAst().getVariables());
        });
    return new SymbolicSrPolicyExport(
        SCHEMA_NAME,
        SCHEMA_VERSION,
        SymbolicControlPlaneExport.guardVariablesFor(variables, linkFailureKeysByGuardVariable),
        records);
  }

  @JsonProperty("schemaName")
  public String getSchemaName() {
    return SCHEMA_NAME;
  }

  @JsonProperty("schemaVersion")
  public int getSchemaVersion() {
    return SCHEMA_VERSION;
  }

  @JsonProperty("guardVariables")
  @Nonnull
  public ImmutableList<SymbolicControlPlaneExport.GuardVariable> getGuardVariables() {
    return _guardVariables;
  }

  @JsonProperty("records")
  @Nonnull
  public ImmutableList<SymbolicSrPolicyRecord> getRecords() {
    return _records;
  }

  public String toJson() {
    try {
      return BatfishObjectMapper.writePrettyString(this);
    } catch (JsonProcessingException e) {
      throw new IllegalStateException("failed to serialize symbolic SR-policy export", e);
    }
  }
}
