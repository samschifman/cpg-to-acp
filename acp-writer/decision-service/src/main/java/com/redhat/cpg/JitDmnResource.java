package com.redhat.cpg;

import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;

import jakarta.ws.rs.Consumes;
import jakarta.ws.rs.POST;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.core.MediaType;
import jakarta.ws.rs.core.Response;

import org.drools.io.InputStreamResource;
import org.kie.dmn.api.core.DMNContext;
import org.kie.dmn.api.core.DMNDecisionResult;
import org.kie.dmn.api.core.DMNModel;
import org.kie.dmn.api.core.DMNResult;
import org.kie.dmn.api.core.DMNRuntime;
import org.kie.dmn.core.internal.utils.DMNRuntimeBuilder;

@Path("/jit/dmn")
public class JitDmnResource {

    public static class JitRequest {
        public String dmn_xml_base64;
        public Map<String, Object> inputs;
    }

    @POST
    @Consumes(MediaType.APPLICATION_JSON)
    @Produces(MediaType.APPLICATION_JSON)
    public Response evaluate(JitRequest request) {
        if (request.dmn_xml_base64 == null || request.inputs == null) {
            return Response.status(400)
                .entity(Map.of("error", "dmn_xml_base64 and inputs are required"))
                .build();
        }

        try {
            byte[] dmnBytes = Base64.getDecoder().decode(request.dmn_xml_base64);
            var resource = new InputStreamResource(
                new ByteArrayInputStream(dmnBytes));

            DMNRuntime runtime = DMNRuntimeBuilder.fromDefaults()
                .buildConfiguration()
                .fromResources(java.util.Collections.singletonList(resource))
                .getOrElseThrow(e -> new RuntimeException("Failed to build DMN runtime: " + e));

            var models = runtime.getModels();
            if (models.isEmpty()) {
                return Response.status(400)
                    .entity(Map.of("error", "No DMN models found in the provided XML"))
                    .build();
            }

            DMNModel model = models.get(0);

            DMNContext context = runtime.newContext();
            for (Map.Entry<String, Object> entry : request.inputs.entrySet()) {
                context.set(entry.getKey(), entry.getValue());
            }

            DMNResult result = runtime.evaluateAll(model, context);

            if (result.hasErrors()) {
                return Response.status(422)
                    .entity(Map.of(
                        "error", "DMN evaluation errors",
                        "messages", result.getMessages().stream()
                            .map(m -> m.getText())
                            .toList()))
                    .build();
            }

            Map<String, Object> outputs = new LinkedHashMap<>();
            for (DMNDecisionResult dr : result.getDecisionResults()) {
                outputs.put(dr.getDecisionName(), dr.getResult());
            }

            return Response.ok(outputs).build();

        } catch (Exception e) {
            return Response.status(500)
                .entity(Map.of("error", "DMN evaluation failed: " + e.getMessage()))
                .build();
        }
    }
}
